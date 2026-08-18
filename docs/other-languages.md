# Julia, R and MATLAB — what actually works

The ICOS zarr service is **plain HTTP**: Zarr v2 stores served as static
objects, plus a REST query API that streams tabular results. Nothing about it
is Python-specific — the Python examples in this repo are the best-developed
ones, not the only possible ones.

**Every Julia and R snippet below was executed against the live service** on
2026-08-18 (R 4.3.3 with httr2 + arrow 25.0.0; Julia 1.10.4 with HTTP.jl,
JSON3, DataFrames and Zarr.jl) and the outputs quoted are what came back. The
MATLAB section is the exception and says so.

All three agree on the same query — one station, one year, QC applied:
**8701 rows, mean CO₂ 426.837 ppm** — which is also what the Python route
returns.

## The two routes

| Route | Julia | R |
|---|---|---|
| **REST `/query`** — server does bbox/time/station/QC filtering, streams a table | works | works |
| **Direct Zarr** — lazy, chunk-level access | *partial* — numeric arrays only, never the QC flags | **no** — `Rarr` returns fill values silently |

For both languages the **REST route is the recommendation**, and not merely
for convenience. Direct Zarr from a non-Python client is where the sharp edges
are: `Zarr.jl` cannot read our QC-flag arrays at all (so you cannot apply QC
yourself), and `Rarr` cannot read this service at all (and says so only by
handing back `NaN`). Filtering server-side with `apply_qc=true` sidesteps both
and returns exactly the rows the Python recipes return.

## R

### The zero-dependency route: CSV

`read.csv` takes a URL, so with `format=csv` there is nothing to install:

```r
url <- paste0("https://zarr.icos-cp.eu/query?id=icos-obspack.co2.co2",
              "&station=CBW207&start=2023-01-01&end=2024-01-01",
              "&apply_qc=true&format=csv")
df <- read.csv(url)
df$time_co2 <- as.POSIXct(df$time_co2, tz = "UTC")   # keep it UTC, see the trap below
```

→ 8701 rows × 7 columns; `co2` numeric, mean 426.837; only `O` flags present
(the rejected samples are already gone); no NAs.

**`format=csv` is not optional.** Without it the endpoint streams ndjson, and
`read.csv` will happily parse that into seven junk columns named
`X.station.CBW207`, `time_co2.2023.01.01T00.30.00Z`, … rather than failing.
This is the one mistake worth calling out, because it produces a data frame
that *looks* real.

### The full-fidelity route: Arrow

```r
library(httr2); library(arrow)

req <- request("https://zarr.icos-cp.eu/query") |>
  req_url_query(id = "icos-obspack.co2.co2", station = "CBW207",
                start = "2023-01-01", end = "2024-01-01",
                apply_qc = "true", max_rows = 200000, format = "arrow")
df <- read_ipc_stream(resp_body_raw(req_perform(req)))    # -> a tibble
```

→ the same 8701 rows, with `time_co2` already `POSIXct` and `co2` numeric.
`format=parquet` behaves the same via `arrow::read_parquet()` on a
`websave`d file.

**Timezone trap.** The returned `POSIXct` carries **no `tzone` attribute**, so
R prints it in the session's timezone — on a machine set to `Europe/Berlin`
the first January timestamp displays as `01:30` where the CSV route says
`00:30`. Same instant, different presentation, and an hour of silent skew in
anything diurnal. Set it explicitly:

```r
attr(df$time_co2, "tzone") <- "UTC"
```

### The passport, in R

Arrow and Parquet carry the RO-Crate data passport in the schema metadata, and
R can read it:

```r
tbl <- read_ipc_stream(resp_body_raw(req_perform(req)), as_data_frame = FALSE)
pp  <- jsonlite::fromJSON(tbl$schema$metadata[["data_passport"]],
                          simplifyVector = FALSE)
length(pp[["@graph"]])    # 6 nodes: the crate root, this query, the variable,
                          # the station, the source objects, the licence
```

Pass `simplifyVector = FALSE`, or jsonlite folds `@graph` into a data frame and
`length()` then counts *columns* rather than nodes — it will tell you there are
30 of them.

CSV cannot carry this at all (a passport is ~7 KB even for two rows, more than
an HTTP header block holds), so a CSV response instead carries
`X-Data-Citation`, `X-Data-License` and `X-Data-DOI` headers — enough to cite
correctly, not enough to reproduce the query. **Use Arrow or Parquet for
anything you intend to publish.**

Reading those headers in R needs a GET whose response you keep —
`curlGetHeaders()` issues a **HEAD**, and `/query` answers `405` to that:

```r
r <- curl::curl_fetch_memory(url)
grep("^x-data-citation", curl::parse_headers(r$headers), value = TRUE, ignore.case = TRUE)
```

### Direct Zarr in R — don't

`Rarr` (Bioconductor) is the obvious candidate, and it **does not work against
this service — silently**:

```r
Rarr::read_zarr_array("https://zarr.icos-cp.eu/icos-obspack.zarr/CBW207/co2",
                      index = list(1:5))
#> NaN NaN NaN NaN NaN        <- the fill value, not the data
```

No error, no warning: just an array of `NaN` where the real values are
`360.125, 361.331, 361.537` (Zarr.jl and Python both read them correctly from
the same URL, and the chunk is served fine — `HTTP 200, 107866 bytes`). On a
whole-array read it does surface something, but only as
`Start tag expected, '<' not found` — an **XML** parse error, which is the
clue: `Rarr` expects an **S3-compatible** endpoint and lists objects through
the S3 XML API. Against an S3-backed store it works perfectly (verified on a
public IDR store, which returned real pixel values); against our plain static
HTTPS server it does not.

So in R the direct-Zarr route is not available today, and its failure mode is
the dangerous kind — a full column of `NaN` that looks like missing data
rather than a broken reader. **Use the REST route.** If direct access from R
ever becomes important, the fix is on our side: serve the stores through an
S3-compatible endpoint as well.

## Julia

### REST

The snippet works as written, but type the columns explicitly — building a
`DataFrame` straight from `JSON3` values yields an abstract `Real` column and
timestamps left as `String`, which is slow and awkward downstream:

```julia
using HTTP, JSON3, DataFrames, Dates

q = Dict("id" => "icos-obspack.co2.co2", "station" => "CBW207",
         "start" => "2023-01-01", "end" => "2024-01-01",
         "apply_qc" => "true", "max_rows" => "200000")
body  = String(HTTP.get("https://zarr.icos-cp.eu/query"; query=q).body)
lines = split(body, '\n'; keepempty=false)
rows  = [JSON3.read(l) for l in lines[1:end-1]]   # last line is the data passport

df = DataFrame(
    station = String[r.station for r in rows],
    time    = DateTime[DateTime(r.time_co2, dateformat"yyyy-mm-ddTHH:MM:SSZ") for r in rows],
    co2     = Float64[r.co2 for r in rows],
)
```

→ 8701 rows, column types `String, DateTime, Float64`, times
`2023-01-01T00:30:00` → `2023-12-31T23:30:00` (note the **exclusive** end),
mean 426.837.

The passport is the last line, and the citation is one lookup away:

```julia
pp    = JSON3.read(lines[end])._passport
root  = first(filter(n -> get(n, "@id", "") == "./", pp["@graph"]))
root["citation"], root["license"]
```

### Direct Zarr — works for data, not for flags

`Zarr.jl` does reach our stores over HTTPS and reads the consolidated
metadata, but **`zopen` on a group fails** on any group containing a
`*_qc_flag` array:

```
ERROR: MethodError: Cannot `convert` an object of type String
       to an object of type Zarr.ASCIIChar
```

The cause is on the reader's side, not in the data: Zarr v2 requires the
`fill_value` of a fixed-width bytes array (`|S1`) to be **base64-encoded**, so
ours is `"LQ=="` (a `-`), and `Zarr.jl` tries to convert that string to a
character without decoding it. `zopen` reads every array's metadata eagerly,
so one flag array takes the whole group down with it.

Addressing an array directly works:

```julia
using Zarr
a = zopen("https://zarr.icos-cp.eu/icos-obspack.zarr/CBW207/co2")
a[1:3]          # Float32[360.125, 361.33102, 361.53702]
```

(It warns `Missing .zmetadata` — harmless, it just means consolidated
metadata was not found at the array level.) The `time_co2` array comes back as
raw `Int32`; decoding it needs the CF `units` attribute applied by hand,
which `xarray` does for you in Python and `Zarr.jl` does not.

The practical consequence: **you cannot apply QC client-side in Julia**,
because the flag arrays are exactly the ones that will not load. Use
`apply_qc=true` on the REST route and let the server do it.

## MATLAB — *not tested*

No MATLAB was available to run these, so unlike everything above this section
is from documentation and should be treated as a starting point, not a
promise. If you try it, please open an issue saying what actually happened.

- **CSV → `readtable`.** `readtable` accepts an HTTPS URL, so `format=csv`
  should give a one-liner with no toolbox. Expected to be the easiest route,
  with the same "don't forget `format=csv`" caveat as R.
- **OPeNDAP → `ncread`.** MATLAB's netCDF interface speaks DAP natively, so
  the gridded route (notebook 06) should work unchanged and server-side.
- **Parquet → `websave` + `parquetread`.** Two lines rather than one, since
  `parquetread` wants a local file. Whether MATLAB exposes the custom
  `data_passport` schema metadata is **unverified** — if it does not, the
  passport is out of reach on this route.
- **Direct Zarr.** MATLAB gained `zarrread`/`zarrinfo` in R2025a. Whether it
  opens a plain HTTPS store, and how it handles the base64 `|S1` fill values
  that trip `Zarr.jl`, are both unknown. Someone with a licence can settle
  this in ten minutes, and it decides whether MATLAB gets a lazy route at all.

## Planned deliverables

1. **`julia/` and `r/` folders with runnable starter scripts** — the three
   recipes above (station series, filtered extract with passport, cruise
   track for a map) as files rather than fragments in a document.
2. **A runner that executes them weekly**, like the notebook check. This is
   the deciding constraint on how many examples we take on: better three that
   are verified every week than a dozen that quietly rot. The Julia/R install
   is the only new cost — the harness already exists.
3. **Settle the MATLAB questions above** and promote that section out of
   "not tested".
4. **A passport-only response** (e.g. `format=passport`), so provenance is one
   plain-JSON request in any language. Today a CSV or MATLAB user has no
   one-line way to get the crate, which is the weakest point in the
   cross-language story — and the cheap workaround, a `HEAD` request for just
   the citation headers, is not available either: `/query` answers **405** to
   `HEAD`. Supporting `HEAD`, or adding this route, would fix the same gap.

## What we are *not* planning

A full R, Julia or MATLAB client library. The service is deliberately plain
HTTP with self-describing metadata; wrapping it per language would add a
maintenance burden and another thing to keep in sync with the API. Worked
examples plus the [reference](zarr-proxy-reference.md) should be enough — if
they are not, that is useful feedback, so please open an issue.
