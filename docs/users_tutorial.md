# Accessing ICOS data from Python — which route, and when

**Draft for discussion.** Every code block below was executed against the live
services on 2026-08-14; timings come from a single machine and are indicative,
not benchmarks.

ICOS data can be reached in several ways. They are not alternatives of equal
standing — each is the best tool for a different question, and picking the wrong
one is usually the difference between three lines of code and an afternoon.

*Assumes working familiarity with `pandas` and `xarray`; everything ICOS-specific
is explained. New to xarray? The [xarray tutorial](https://tutorial.xarray.dev)
is the fastest way in.*

## 1. Choose your route in 30 seconds

| Your situation | Route | Why |
|---|---|---|
| I need *the* citable file behind a figure in my paper | **`icoscp_core`** object access | Provenance, DOI and licence attach to the data object |
| I want a station's full time series for analysis | **Zarr** store | Merged across releases, longest coverage, loads lazily |
| I need a slice of a large gridded netCDF (inversion, emission inventory) | **OPeNDAP** + `pydap` | Subsets server-side; no multi-GB download |
| I want a quick filtered extract, minimal setup | **REST `/query`** | One URL returns NDJSON / Arrow / Parquet |
| I need metadata for many objects at once | **`icoscp_core`** metadata / SPARQL | Structured and batchable |

Rules of thumb: **analysis → Zarr, citation → portal object, big grids →
OPeNDAP.** When in doubt, start with Zarr and fall back to the portal object when
you need the exact released file.

## 2. Setup, once

```bash
pip install icoscp_core xarray zarr pydap netcdf4
```

```python
from icoscp_core.icos import bootstrap
auth, meta, data = bootstrap.fromPasswordFile("~/.icoscp_auth")   # asks once, then caches
```

Anonymous access works for the Zarr stores and the REST API. Portal objects and
OPeNDAP need the token above. On the ICOS JupyterHub the credentials file is
already in your home directory.

## 3. Finding what exists

Before you can load anything you need a station, a data type, or an object id.
All three listings are cheap (they are cached SPARQL queries — well under a
second) so explore them interactively.

```python
stations = meta.list_stations()                 # 470 stations, all domains
types    = meta.list_datatypes()                # 128 data types

cbw = next(s for s in stations if s.id == "CBW")
print(cbw.name, cbw.uri)     # Cabauw  http://meta.icos-cp.eu/resources/stations/AS_CBW

spec = "http://meta.icos-cp.eu/resources/cpmeta/atcCo2L2DataObject"   # ICOS ATC CO2 Release
dobjs = meta.list_data_objects(datatype=spec, station=cbw.uri)
for d in dobjs:
    print(d.filename, d.uri.split("/")[-1], d.size_bytes)
# ICOS_ATC_L2_L2-2026.1_CBW_207.0_CTS_CO2.zip  0iQnqctEYJ-jM0ERHkXmVUO8  792297
# ...one object per intake height (27, 67, 127, 207 m)
```

Note the shape of the answer: a tall tower yields **one object per intake
height**, exactly like the Zarr station groups. Whichever route you take, you
must choose a height.

For anything the three listings cannot express, `meta.sparql_select(query)` runs
arbitrary SPARQL against the metadata store. The browser UI at
<https://data.icos-cp.eu/portal/> is the fastest way to explore visually — the
last path segment of a landing-page URL is the object id used below.

Reading many objects at once is a single call, and fast:

```python
for dobj, cols in data.batch_get_columns_as_arrays(dobjs, ["TIMESTAMP", "co2"]):
    print(dobj.filename, len(cols["co2"]))
# 3 objects, 118,368 rows, 0.2 s
```

## 4. The same question, four ways

*Monthly mean CO₂ at Cabauw, 207 m intake, 2023.*

### Zarr — the analysis route

```python
import numpy as np, pandas as pd, xarray as xr

# Open the GROUP URL directly — opening the store root with group= downloads
# the whole store's consolidated metadata (~16 MB raw) instead of the group's
# ~0.2 MB, costing seconds per open.
ds = xr.open_zarr("https://zarr.icos-cp.eu/icos-obspack.zarr/CBW207",
                  consolidated=True)                     # station + intake height
co2   = np.asarray(ds["co2"].values, dtype=float)        # ppm
flags = np.array([f.decode() for f in ds["co2_qc_flag"].values])
time  = pd.to_datetime(ds["time_co2"].values)

good = np.isin([f[:1] for f in flags], ["O", "U"])       # keep only usable data
monthly = pd.Series(co2[good], index=time[good])["2023"].resample("MS").mean()
```

### Portal object — the citable route

```python
dobj = meta.get_dobj_meta("https://meta.icos-cp.eu/objects/0iQnqctEYJ-jM0ERHkXmVUO8")
cols = data.get_columns_as_arrays(dobj)                  # no file written
print(dobj.references.citationString)                    # cite THIS in your paper
```

Use `data.save_to_folder(dobj, ".")` when you want the file itself.

### REST — the no-dependencies route

```python
url = ("https://zarr.icos-cp.eu/query?id=icos-obspack.co2.co2"
       "&station=CBW207"                    # trigram + intake height, directly
       "&start=2023-01-01&end=2024-01-01&apply_qc=true&max_rows=200000")
df = pd.read_json(url, lines=True)
assert set(df.station.dropna()) == {"CBW207"}   # cheap sanity check
```

`station=` takes a comma-separated list and is the direct form of a bounding
box + height window (`lat_min/lat_max/lon_min/lon_max` +
`height_min=200&height_max=210`), which remain available for spatial
selections. Unknown station ids are a loud HTTP 400.

### OPeNDAP — the netCDF route

The same series also exists as an ObsPack netCDF object, one per station ×
intake height × gas — find its id with
`meta.list_data_objects(datatype=<Obspack CO2 time-series result>, station=cbw.uri)`.
Open it remotely with the portal token (section 2):

```python
import requests
session = requests.Session()
session.headers.update({"Authorization": "Bearer " + auth.get_token().cookie_value})

OBJECT_ID = "2QX5BX64k47kopRawJmsFCSF"           # co2_cbw_tower-insitu_445_207magl.nc
ds = xr.open_dataset(f"dap2://opendap.icos-cp.eu/{OBJECT_ID}",
                     engine="pydap", backend_kwargs={"session": session})
co2  = np.asarray(ds["value"].values, dtype=float) * 1e6   # mol/mol → ppm
time = pd.to_datetime(ds["time"].values)
monthly = pd.Series(co2, index=time)["2023"].dropna().resample("MS").mean()
```

Two ObsPack-netCDF quirks: values are **mol/mol** (multiply by 1e6 for ppm), and
there is no letter QC flag — rejected samples are already NaN, so `dropna()` is
the QC filter. The DAP handshake costs ~6 s per object before any data moves,
which is why this route earns its keep on large gridded files (section 5), not
on point time series.

### What it cost

| Route | Time | Points returned | Result |
|---|---|---|---|
| Zarr station group (group URL) | 1.2 s warm (~4 s first touch) | 8,701 | 426.84 ppm |
| Portal object (`get_columns_as_arrays`) | 0.4 s | 8,701 | 426.84 ppm |
| REST `/query` (`station=CBW207`) | 0.4 s | 8,701 | 426.84 ppm |
| OPeNDAP (ObsPack netCDF, token) | 6.5 s (5.7 s open + 0.8 s read) | 8,701 | 426.84 ppm |

All four routes agree **exactly**: `apply_qc=true` drops the same rows the
letter-flag recipe drops (keep first character `O`/`U`), and `end` is
exclusive on every store. Without a `station`/height selection, a bounding box
around a tall tower returns every intake height — select the level explicitly.
(Measured 2026-08-16 from a home connection. The zarr route's first touch pays
connection setup plus the server pulling that group's chunks into its page
cache — repeat reads run ~1 s. Values will drift as releases land; the
agreement won't.)

## 5. Large gridded netCDF — OPeNDAP

For inversions, emission inventories and model output, do not download the file.
Open it remotely and slice first:

```python
import os, requests, xarray as xr
session = requests.Session()
session.headers.update({"Authorization": "Bearer " + auth.get_token().cookie_value})

OBJECT_ID = "nSEUnW0USDG3ItrwyW1Rjlhk"           # anthropogenic emissions, per sector
ds = xr.open_dataset(f"dap2://opendap.icos-cp.eu/{OBJECT_ID}",
                     engine="pydap", backend_kwargs={"session": session})
print(ds)                                        # 672 × 390 × 250 — inspect first!
subset = ds["A_Public_power"].isel(time=0)       # then take what you need
```

Metadata and a small slice come back in seconds; reading the whole field would
move gigabytes.

## 6. Ecosystem and ocean, one recipe each

The Zarr route is the same shape in every domain; only the store and the
grouping convention change.

**Ecosystem fluxes (FLUXNET).** Groups are site codes — the ICOS station URI
suffix after `ES_` — with one subgroup per aggregation. Open the aggregation you
need; never resample daily data to months yourself.

```python
ds = xr.open_zarr("https://zarr.icos-cp.eu/icos-fluxnet.zarr",
                  group="SE-Htm/fluxnet_mm", consolidated=True)   # Hyltemossa, monthly
nee = ds["NEE"].where(ds["NEE_QC"] > 0.3)        # QC is a fraction here, not a flag
```

Aggregations: `fluxnet_dd` (daily), `fluxnet_ww`, `fluxnet_mm`, `fluxnet_yy`.
The `_combined/…` groups stack all 43 sites on a `station` dimension.

**Surface-ocean CO₂ (SOCAT).** Groups are expocodes, `<PLATFORM><STARTDATE>`.
The ship name lives only in the `station_name` attribute, so build an index once:

```python
import zarr
root = zarr.open_group("https://zarr.icos-cp.eu/icos-socat.zarr", mode="r")
finnmaid = [(g, a["time_start"][:10], a["time_end"][:10])
            for g in root.group_keys()
            for a in [dict(root[g].attrs)]
            if "finnmaid" in str(a.get("station_name", "")).lower()]     # 46 cruises

ds = xr.open_zarr("https://zarr.icos-cp.eu/icos-socat.zarr",
                  group="34FM20240623", consolidated=True)
df = ds[["lat", "lon", "pCO2", "pCO2_QC"]].to_dataframe()
df = df[df.pCO2_QC == 2]                         # WOCE: 2 = good
```

Select cruises by `time_start`/`time_end`, not by the name — the date in an
expocode is the cruise *start*, so a 2023-named cruise can hold January-2024 data
(pitfall 2).

## 7. When something misbehaves

Conventions, traps and costs live in **[users_reference.md](users_reference.md)** —
identifier naming per store, the quality-flag table, what each operation costs,
and the pitfalls that account for most lost afternoons. Worth skimming once
before your first real analysis.

## 8. Demo applications — and their source as example code

<https://zarr.icos-cp.eu> links five interactive viewers built on exactly the
routes described here. They are useful twice over: as a quick way to see what a
dataset contains before writing any code, and as **worked source code** for the
access patterns — store selection, QC filtering, time and bbox subsetting,
passport handling.

| Application | Data |
|---|---|
| [ICOS multi-domain data browser](https://icos-data-viewer.icos-cp.eu/) | all stores, side by side |
| [ICOS ObsPack atmosphere viewer](https://icos-obspack-viewer.icos-cp.eu/) | `icos-obspack.zarr` |
| [FLUXNET Shuttle viewer](https://fluxnet-viewer.icos-cp.eu/) | `icos-fluxnet.zarr` |
| [SOCAT ocean viewer](https://socat-viewer.icos-cp.eu/) | `icos-socat.zarr`, `socat-gridded.zarr` |
| [NOAA GlobalView atmosphere viewer](https://globalview.icos-cp.eu/) | GlobalView (login required) |

If you are building something similar, start from the viewer closest to your
domain rather than from a blank notebook.

## 9. Worked examples (notebooks on the JupyterHub)

Each notebook takes one route end to end; start here if you prefer running code
to reading it.

| Notebook | Route | You will learn |
|---|---|---|
| 1. Quickstart | `icoscp_core` | search → inspect → load → cite |
| 2. Atmosphere time series | Zarr (ObsPack) | QC filtering, monthly means, growth rate |
| 3. Ecosystem fluxes | Zarr (FLUXNET) | aggregation groups, NEE seasonal cycle |
| 4. Ocean ship tracks | Zarr (SOCAT) | cruise selection, pCO₂ track map |
| 5. Large gridded data | OPeNDAP | remote subsetting of an inventory |
| 6. Reproducibility | all | tokens, citations, data passports |

*(links added as each notebook lands)*

## 9. Citing what you used, and data passports

Every route can hand you the citation string. Never write one yourself, and
never reconstruct a DOI — take it from the data.

### Zarr stores

Each station, site or cruise group carries its own citation, DOI and licence:

```python
ds = xr.open_zarr(BASE, group="34FM20240623", consolidated=True)
ds.attrs["citation"]        # 'Rehder, G., Bittig, H., … ICOS OTC SOOP Release from Finnmaid, …'
ds.attrs["source_doi"]      # the released object this group was built from
ds.attrs["collection_doi"]  # the collection it belongs to, where one exists
ds.attrs["license"]         # CC-BY-4.0
ds.attrs["_provenance"]     # when the group was built, and from what
```

FLUXNET aggregation subgroups (`SE-Htm/fluxnet_mm`) carry their own `citation`
and `source_doi` — cite the group you actually opened.

**ObsPack is per species.** A station group holds CO₂, CH₄, CO, N₂O, ²²²Rn and
¹⁴CO₂ together, each with its own provenance, so cite the species you used:

```python
ds.attrs["co2_dobj_citation"]       # the ICOS data object the CO2 came from
ds.attrs["co2_obspack_citation"]    # the ObsPack product it was compiled into
ds.attrs["co2_provider_citations"]  # list — the station PIs who produced it
ds.attrs["co2_source_doi"]
```

Where a product bundles many contributors, `*_provider_citations` is the list
that credits them; include it when your analysis rests on a small number of
stations.

### A whole store

If your analysis spans many groups, cite the store itself. Each one publishes
Croissant metadata with a ready-made citation and its own DOI:

```python
import requests
c = requests.get("https://zarr.icos-cp.eu/icos-obspack.zarr/croissant").json()
c["citeAs"], c["url"], c["license"]
```

| Store | DOI |
|---|---|
| `icos-obspack.zarr` | https://doi.org/10.18160/JZ2X-GZGU |
| `icos-fluxnet.zarr` | https://doi.org/10.18160/S6TB-567H |
| `icos-socat.zarr` | https://doi.org/10.18160/BCFM-GNVA |

Cite the most specific thing you actually used — the station or cruise group —
and add the store DOI for the compilation itself.

### Portal objects

```python
dobj.references.citationString
```

### OPeNDAP

An OPeNDAP dataset exposes the licence but **not** the citation, so fetch it from
the metadata service using the same object id:

```python
ds.attrs["license"]                                  # CC-BY-4.0 — that is all there is
cit = meta.get_dobj_meta(f"https://meta.icos-cp.eu/objects/{OBJECT_ID}").references.citationString
```

### Data passports

A REST `/query` response ends with a **data passport** — an RO-Crate JSON-LD
record of exactly what that query touched, returned as the last NDJSON line:

```python
import json, pandas as pd
lines = pd.read_json(url, lines=True)          # …or read the raw text
passport = json.loads(raw.splitlines()[-1])["_passport"]
```

Inside it you get the citation, `license` and `collection_doi`; `accessedGroups`
and `accessedArrays` naming the exact store paths read; `dateAccessed`;
`rowCount` and `sizeInBytes`; and a `passportSha256` integrity hash.

That combination is what makes a query reproducible rather than merely repeatable:
it records *which* slice of *which* release you analysed, on *what date*. **Save
the passport next to your results** — in a paper's supplementary material it does
the job that a screenshot of a download page cannot.

```python
import json
json.dump(passport, open("results/passport.json", "w"), indent=2)
```

**Direct Zarr reads get a passport too.** Every chunk you read through
`zarr.icos-cp.eu` is aggregated into a per-client session. Ask for the passport
when you're done — the request closes the session and returns it immediately:
the same RO-Crate record (accessed groups and arrays, byte counts, access date,
citation, licence, integrity hash), also archived server-side.

```python
import requests
r = requests.get("https://zarr.icos-cp.eu/icos-obspack.zarr/session/passport").json()
passport = r["passport"]      # full RO-Crate JSON-LD, delivered on request
```

Reads after the call simply start a new session (`?status=true` peeks without
closing; idle sessions close on their own after ~5 minutes, and a closed
session's passport stays retrievable for an hour from the same machine).
Save this passport exactly like the `/query` one.

The stores are live (`isLiveDataset: true` in the Croissant metadata) — they grow
as new releases land. If you read a **local copy** of a store (outside the
proxy), no session exists, so record the equivalent yourself:

```python
import datetime, json
json.dump({
    "store":     "https://zarr.icos-cp.eu/icos-obspack.zarr",
    "group":     "CBW207",
    "variables": ["co2", "co2_qc_flag"],
    "accessed":  datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    "citation":  ds.attrs["co2_dobj_citation"],
    "source_doi": ds.attrs["co2_source_doi"],
    "store_doi": "https://doi.org/10.18160/JZ2X-GZGU",
    "license":   ds.attrs["license"],
}, open("results/provenance.json", "w"), indent=2)
```

Because the stores are live, **the access date is not optional** — the same group
queried a year apart will not return the same series.

### A data availability statement

> Atmospheric CO₂ observations were obtained from the ICOS Carbon Portal ObsPack
> Zarr store (https://doi.org/10.18160/JZ2X-GZGU), group `CBW207`
> (Cabauw, 207 m intake), accessed 2026-08-14, and are licensed CC-BY-4.0.
> *[citation string from the group attributes]*. Only observations flagged `O` or
> `U` were used.

For large extracts, `format=arrow` and `format=parquet` return the same data as
a binary stream with the passport in the schema metadata under `data_passport`.
They work for every store, ObsPack included; character QC flags such as
`co2_qc_flag` arrive as strings, exactly as in `ndjson`. Arrow is the fast bulk
route: a full 227k-row station series is 3.5 MB and arrives in ~1.3 s, parsing
in milliseconds (`pyarrow.ipc.open_stream(...).read_all().to_pandas()`), where
the same series as ndjson is 36 MB of text. ndjson responses are gzipped when
the client sends `Accept-Encoding: gzip` (`requests` does; plain
`pd.read_json(url)` does not — fine for a station-year, wasteful beyond that).

All ICOS data are **CC-BY-4.0**: cite, and state any modifications.
