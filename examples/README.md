# Standalone examples

Scripts that run as-is against <https://zarr.icos-cp.eu>, and that you can
also import as functions. The notebooks teach one idea at a time; these are
closer to what an analysis script looks like in practice.

| Script | What it does |
|---|---|
| [`obspack_class12_stats.py`](obspack_class12_stats.py) | For every ICOS **Class 1 + Class 2** atmosphere station, pull the QC-passed hourly CO₂/CH₄/CO/N₂O series, write a regular-hourly station matrix, and compute pooled **monthly statistics** (mean + 5th…95th percentiles in steps of 5, timestamped mid-month). Output as csv / pyarrow / netcdf / parquet. |

## Other languages

The service is plain HTTP, so it is not Python-only. These were **executed
against the live service** and return the same 8701 rows and mean of
426.837 ppm as the Python route:

| Script | Notes |
|---|---|
| [`r/station_series_csv.R`](r/station_series_csv.R) | Base R, no packages — `format=csv` straight into `read.csv` |
| [`r/station_series_arrow.R`](r/station_series_arrow.R) | httr2 + arrow, with the full data passport; use this for published work |
| [`julia/station_series.jl`](julia/station_series.jl) | HTTP.jl + JSON3 + DataFrames |
| [`octave/station_series.m`](octave/station_series.m) | GNU Octave, no packages — both the CSV and the passport-carrying ndjson route |

Each one carries the trap it took a test run to find — the missing
`format=csv` that turns ndjson into seven junk columns, the Arrow timestamps
with no timezone attribute, the abstractly-typed Julia columns. See
[`docs/other-languages.md`](../docs/other-languages.md) for the full account,
including why direct Zarr access is not usable from R today.

Use it either way:

```python
from obspack_class12_stats import compute_class12_stats

results = compute_class12_stats()                      # defaults: proxy, /tmp, parquet
results = compute_class12_stats(out_dir="./out", file_format="netcdf",
                                gases=("co2", "ch4"))
```

```bash
python obspack_class12_stats.py --out-dir ./out --format parquet --gases co2
```

A note on where the computation happens: the zarr proxy serves *chunks*, not
computations, so the chunks travel to wherever the script runs and dask makes
that streaming and parallel. Run it close to the data (e.g. the ICOS
JupyterHub) and it is effectively server-side; over a home connection it
simply keeps memory flat while it downloads.
