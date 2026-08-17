# Julia and R — what works today, and what we plan to add

The ICOS zarr service is **plain HTTP**: Zarr v2 stores served as static
objects, plus a REST query API that streams tabular results. Nothing about it
is Python-specific — the Python examples in this repo are the best-developed
ones, not the only possible ones. This page states honestly what a Julia or R
user can do **today**, and what we intend to add.

*Status: written 2026-08. The "today" column is what the service already
supports; the deliverables are proposals, not yet shipped.*

## The two routes, in any language

| Route | What you need | Julia | R |
|---|---|---|---|
| **REST `/query`** — server does bbox/time/station/QC filtering, streams a table | An HTTP client and a table reader | `HTTP.jl` + `Arrow.jl` / `JSON3.jl` | `httr2` + `arrow` / `jsonlite` |
| **Direct Zarr** — lazy, chunk-level access to whole stores | A Zarr v2 reader | `Zarr.jl`, `YAXArrays.jl` | `Rarr` (Bioconductor) |

Our stores are **Zarr v2 with consolidated metadata**, which is the format
both `Zarr.jl` and `Rarr` support — this is one practical reason the stores
stay v2 (see the migration notes in the main repo).

### Julia today

```julia
using HTTP, JSON3, DataFrames

url = "https://zarr.icos-cp.eu/query"
q = Dict("id" => "icos-obspack.co2.co2", "station" => "CBW207",
         "start" => "2023-01-01", "end" => "2024-01-01",
         "apply_qc" => "true", "max_rows" => "200000")
lines = split(String(HTTP.get(url; query=q).body), '\n'; keepempty=false)
rows  = [JSON3.read(l) for l in lines[1:end-1]]      # last line = data passport
df    = DataFrame(station = [r.station for r in rows],
                  time    = [r.time_co2 for r in rows],
                  co2     = [r.co2 for r in rows])
```

Direct Zarr with `Zarr.jl` / `YAXArrays.jl` works against a group URL
(`https://zarr.icos-cp.eu/icos-obspack.zarr/CBW207`) the same way
`xarray.open_zarr` does in Python.

### R today

```r
library(httr2); library(arrow); library(dplyr)

req <- request("https://zarr.icos-cp.eu/query") |>
  req_url_query(id = "icos-obspack.co2.co2", station = "CBW207",
                start = "2023-01-01", end = "2024-01-01",
                apply_qc = "true", max_rows = 200000, format = "arrow")
df <- read_ipc_stream(resp_body_raw(req_perform(req)))   # Arrow IPC → tibble
```

`format=parquet` works the same way via `arrow::read_parquet()`. If you would
rather not install `arrow` at all, `format=csv` needs nothing beyond base R:

```r
df <- read.csv(paste0("https://zarr.icos-cp.eu/query?id=icos-obspack.co2.co2",
                      "&station=CBW207&start=2023-01-01&end=2024-01-01&apply_qc=true"))
```

For direct Zarr access, `Rarr::read_zarr_array()` reads our v2 arrays over
HTTPS.

## Gaps we found while writing this — and what we did about them

1. **No CSV output.** `format=` accepted only `ndjson`, `arrow` and
   `parquet`. CSV is the lingua franca for R and spreadsheet users, and its
   absence was a real barrier. **Fixed: `format=csv` now returns plain
   RFC-4180 text** that loads with a bare `read.csv()` — no `skip=`, no
   `comment.char=`, nothing to explain first.
2. **An unsupported `format=` silently returned ndjson**, so `format=csv`
   looked like it worked and quietly gave you something else. That
   contradicted the service's own "a filter that cannot apply fails loud"
   contract. **Fixed: unknown formats now answer 400 and name the valid
   choices.**
3. **The passport is easy to lose in a non-Python client.** In ndjson it is
   the last line; in Arrow/Parquet it is schema metadata. Both are readable
   from Julia and R, but our examples never showed how.

A caveat worth stating plainly, because it decides which format to
recommend: **CSV cannot carry the passport.** A passport is ~7 KB even for a
two-row result, which is more than an HTTP header block can hold, so a CSV
response carries only `X-Data-Citation`, `X-Data-License` and `X-Data-DOI`
headers — enough to cite the data correctly, not enough to reproduce the
query. So CSV is the right default for a quick look and for handing data to
a colleague, and **Parquet is the right default for analysis you intend to
publish**, in every language. The R and Julia examples should teach the
Parquet habit and mention CSV, not the other way round.

## Planned deliverables

Ordered by value per unit of work; each is a small, self-contained addition
to this repo.

1. **`julia/` and `r/` folders with the three "starter" recipes**, mirroring
   the simplest Python notebooks so a newcomer can copy one file:
   - a station time series with QC applied (notebook 02's core),
   - a filtered REST extract into a data frame, **keeping the passport**
     (notebook 03's core),
   - an ocean cruise track for a map (notebook 05's core).
2. **A CSV example** in both languages, showing the citation headers so the
   provenance caveat above is visible where people will actually meet it.
3. **A short "reading the data passport" snippet** per language, since
   provenance is the part most likely to be dropped when people port code.
4. **Direct-Zarr examples** — `Zarr.jl`/`YAXArrays.jl` and `Rarr` — showing
   the group-URL habit (open the station group, not the store root) that
   makes reads fast.
5. **CI that actually runs them.** The Python notebooks are re-executed
   weekly against the live services; Julia and R examples should be too, or
   they will rot silently. This is the deciding factor for how many we take
   on: better three examples that are verified every week than a dozen that
   quietly stop working.

## What we are *not* planning

A full R or Julia client library. The service is deliberately plain HTTP with
self-describing metadata; wrapping it per language would add a maintenance
burden and another thing to keep in sync with the API. Worked examples plus
the [reference](zarr-proxy-reference.md) should be enough — if they are not,
that is useful feedback, so please open an issue.
