#!/usr/bin/env python3
"""ICOS Class 1/2 ObsPack statistics — importable version.

Call as a subroutine::

    from obspack_class12_stats import compute_class12_stats
    results = compute_class12_stats()                       # all defaults
    results = compute_class12_stats(
        store_url="https://zarr.icos-cp.eu/icos-obspack.zarr",
        out_dir="/data/exports", file_format="netcdf", gases=("co2", "ch4"))

or from the command line::

    python obspack_class12_stats.py [--store URL] [--out-dir DIR]
        [--format csv|pyarrow|netcdf|parquet] [--gases co2 ch4 ...]

Per gas it produces two files in ``out_dir`` (default ``/tmp``, default
format parquet):

- ``obspack_<gas>_class12_hourly.*`` — QC-passed values (ICOS ATC letter
  flags, first character O/U usable) of every ICOS Class 1 + Class 2
  station, resampled per station onto a regular hourly grid (rows labelled
  at the hour start; hours nobody sampled are NaN / empty in CSV); one
  column per station id (trigram+height, e.g. CBW207);
- ``obspack_<gas>_class12_monthly.*`` — the pooled monthly statistics of
  exactly those hourly values: ``month, n_samples, n_stations, mean`` and
  the 5th…95th percentiles in steps of 5, timestamped at mid-month.

The return value maps each gas to its written paths and the statistics
frame: ``{gas: {"hourly": str, "monthly": str, "stats": DataFrame}}``.

The zarr proxy serves chunks, not computations — dask parallelises the
statistics wherever THIS runs; run it next to the store for "server-side".

Requirements: pip install "xarray[complete]" "zarr>=3" dask pandas
pyarrow netcdf4
"""
from __future__ import annotations

import pathlib

import dask
import dask.dataframe as dd
import numpy as np
import pandas as pd
import xarray as xr
import zarr

DEFAULT_STORE = "https://zarr.icos-cp.eu/icos-obspack.zarr"
GASES = ("co2", "ch4", "co", "n2o")
QS = [q / 100 for q in range(5, 100, 5)]            # 0.05 ... 0.95
_EXT = {"csv": "csv", "pyarrow": "feather", "netcdf": "nc", "parquet": "parquet"}


def _class_of(attrs) -> str:
    """Normalise station_class (stored as 1, '1' or 1.0) to '1'/'2'/…/''"""
    raw = attrs.get("station_class", "")
    try:
        return str(int(float(raw)))
    except (TypeError, ValueError):
        return str(raw).strip()


def _month_stats(s: pd.Series) -> pd.Series:
    out = {"n_samples": float(s.size), "mean": s.mean()}
    out.update({f"p{int(q * 100):02d}": v for q, v in s.quantile(QS).items()})
    return pd.Series(out)


_META = _month_stats(pd.Series([1.0, 2.0]))         # dask output schema


def _write(df: pd.DataFrame, stem: pathlib.Path, fmt: str, unit: str,
           what: str, store_url: str) -> str:
    """Write *df* (DatetimeIndex + value columns) in the chosen format."""
    fn = str(stem) + "." + _EXT[fmt]
    if fmt == "csv":
        df.to_csv(fn, float_format="%.3f")          # NaN -> empty string
    elif fmt == "pyarrow":                          # Feather v2 = Arrow IPC
        df.reset_index().to_feather(fn)
    elif fmt == "parquet":
        df.reset_index().to_parquet(fn, compression="zstd", index=False)
    elif fmt == "netcdf":
        ds = df.to_xarray()
        for v in ds.data_vars:
            if np.issubdtype(ds[v].dtype, np.number):
                ds[v].attrs["units"] = unit
        ds.attrs.update(source=store_url, description=what)
        ds.to_netcdf(fn)
    else:
        raise ValueError(f"unknown format {fmt!r} (use {sorted(_EXT)})")
    return fn


def compute_class12_stats(store_url: str = DEFAULT_STORE,
                          out_dir: str | pathlib.Path = "/tmp",
                          file_format: str = "parquet",
                          gases=GASES,
                          verbose: bool = True) -> dict:
    """QC-passed hourly matrices + pooled monthly statistics for all ICOS
    Class 1/2 stations in an ObsPack-layout zarr store. See module docstring.
    """
    if file_format not in _EXT:
        raise ValueError(f"file_format must be one of {sorted(_EXT)}")
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # station -> ICOS class, from ONE consolidated-metadata request
    root = zarr.open_group(store_url, mode="r")   # URL works under zarr>=3
    station_class = {name: _class_of(grp.attrs) for name, grp in root.groups()
                     if "station_name" in grp.attrs}
    class12 = {s for s, c in station_class.items() if c in ("1", "2")}
    if verbose:
        print(f"{len(class12)} of {len(station_class)} station groups are "
              f"ICOS Class 1 or 2")

    results: dict = {}
    for gas in gases:
        panel = xr.open_zarr(f"{store_url}/{gas}", consolidated=True)  # lazy
        tdim = f"time_{gas}"
        wanted = [s for s in map(str, panel["station"].values) if s in class12]
        if not wanted:
            if verbose:
                print(f"{gas}: no Class 1/2 stations in the panel — skipped")
            continue

        sel = panel[[gas, f"{gas}_qc_flag"]].sel(station=wanted).load()
        vals = sel[gas].values.astype("float64")             # (station, time)
        first_char = sel[f"{gas}_qc_flag"].values.astype("U1")
        vals[~np.isin(first_char, ("O", "U"))] = np.nan      # QC: keep O/U
        unit = panel[gas].attrs.get("units", "")

        # regular hourly grid per station (hour-start labels, gaps stay NaN)
        wide = (pd.DataFrame(vals.T, index=pd.to_datetime(sel[tdim].values),
                             columns=wanted)
                .resample("1h").mean())
        wide.index.name = "time"
        hourly_fn = _write(
            wide, out_dir / f"obspack_{gas}_class12_hourly", file_format, unit,
            f"QC-passed hourly {gas} of ICOS Class 1/2 stations, regular "
            f"hourly grid, one column/variable per station (trigram+height)",
            store_url)

        # dask: pooled monthly mean + percentiles over the same hourly values
        long = wide.stack(future_stack=True).dropna()
        long.index.names = ["time", "station"]
        ldf = long.rename("value").reset_index()
        ldf["month"] = ldf["time"].dt.strftime("%Y-%m")
        g = dd.from_pandas(ldf, npartitions=16).groupby("month")
        stats, n_stations = dask.compute(
            g["value"].apply(_month_stats, meta=_META),
            g["station"].nunique())
        out = stats.unstack().sort_index()
        out.insert(1, "n_stations", n_stations)
        out["n_samples"] = out["n_samples"].astype(int)

        # timestamp each month's statistics at the EXACT month middle
        periods = pd.PeriodIndex(out.index, freq="M")
        out.index = (periods.start_time
                     + (periods.end_time - periods.start_time) / 2).round("min")
        out.index.name = "time"
        out.insert(0, "month", periods.astype(str))

        monthly_fn = _write(
            out, out_dir / f"obspack_{gas}_class12_monthly", file_format, unit,
            f"Monthly pooled statistics (mean + p05..p95) of QC-passed hourly "
            f"{gas} over ICOS Class 1/2 stations; timestamps at mid-month",
            store_url)

        if verbose:
            print(f"{gas.upper()} [{unit}] — {len(wanted)} stations, "
                  f"{int(out['n_samples'].sum()):,} QC-passed samples, "
                  f"{len(out)} months → {monthly_fn} + {hourly_fn}")
        results[gas] = {"hourly": hourly_fn, "monthly": monthly_fn,
                        "stats": out}
    return results


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(
        description="Monthly stats + hourly matrix of ICOS Class 1/2 "
                    "ObsPack stations")
    ap.add_argument("--store", default=DEFAULT_STORE,
                    help=f"ObsPack-layout zarr URL (default {DEFAULT_STORE})")
    ap.add_argument("--out-dir", default="/tmp",
                    help="directory for the output files (default /tmp)")
    ap.add_argument("--format", choices=sorted(_EXT), default="parquet",
                    help="output file format (default parquet)")
    ap.add_argument("--gases", nargs="+", choices=GASES, default=list(GASES),
                    help="gases to process (default: all)")
    args = ap.parse_args()
    compute_class12_stats(store_url=args.store, out_dir=args.out_dir,
                          file_format=args.format, gases=args.gases)


if __name__ == "__main__":
    main()
