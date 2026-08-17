# The ICOS Zarr proxy — reference

This is the **canonical** reference for `https://zarr.icos-cp.eu` — what it
serves, how the pieces fit, where every kind of metadata lives, and how to use
it efficiently from Python, plain HTTP, or an AI agent. Condensed copies of
some tables exist in the cp-ai-assist docs (`users_reference.md`); when they
disagree, this document wins. The companion
hands-on material is the [sample notebook series](../notebooks/README.md);
deployment and code-level architecture live in
[proxy-architecture.md](proxy-architecture.md).

---

## 1. Zarr in short — what it is, what it buys us

A **Zarr store** is the simplest possible cloud-native array format: every
N-dimensional array is split into **chunks**, each chunk is a separately
compressed object, and the array's shape, dtype, chunking and attributes are
plain **JSON metadata** next to the chunks. A store is just a directory tree
of these objects — servable by any HTTP server, no data-specific software on
the server side.

Three properties follow, and they are the reason ICOS serves data this way:

- **Partial reads are native.** A client that wants one station's June from a
  30-year archive fetches the JSON metadata plus the handful of chunks under
  that slice — nothing else moves. There is no "subsetting service" in the
  middle; the chunk arithmetic *is* the subsetting service.
- **Opening is instant.** All metadata for a store (or a group) can be
  *consolidated* into one JSON document (`.zmetadata`), so `xarray.open_zarr`
  costs a single request and returns lazy arrays.
- **It parallelises and caches trivially.** Chunks are immutable objects with
  URLs — CDNs, OS page caches and concurrent readers all work without
  coordination.

Compared to the alternatives: a netCDF file must be downloaded (or accessed
through an OPeNDAP service that pays a multi-second handshake per file, see
notebook 06); a database needs a query API designed up front. Zarr gives
array-shaped data the "read only what you need" property with nothing but
static objects — and the proxy described here adds the discovery, provenance
and query conveniences on top.

The stores are **Zarr format v2 with consolidated metadata**, readable by
`zarr`≥2.13 and any recent `xarray` (plus `fsspec`/`aiohttp` for HTTP when
using zarr-python 2.x).

## 2. The proxy: four services in one

`zarr.icos-cp.eu` is one FastAPI service in front of the store directory. It
plays four roles:

**(a) A Zarr HTTP server.** `GET /<store>.zarr/<key>` serves the raw store
objects — metadata documents and chunks — so `xarray.open_zarr(url)` just
works. On top of plain file serving it adds: gzip for JSON metadata, an
mtime-validated open cache (nightly rebuilds grow arrays in place; a stale
handle is never served), and **per-client session recording** — which groups,
arrays, chunks and bytes each anonymised client read. That recording is what
makes data passports possible for direct Zarr access (role d of the reader's
workflow, chapter 5.6).

**(b) A REST query API.** `/query` returns filtered extracts from any
catalogued variable as ndjson, Arrow or Parquet — for users who want "one URL
→ a table" without any Zarr tooling, and for extracts that cross entities
(all stations in a bbox, one ship season, a height window on a tall tower).
`/variables` is the catalogue, `/summary` prices a selection before download.
Chapter 5 specifies it fully.

**(c) Machine and agent discovery.** Every store is self-describing at
several levels of formality: an `agent_guide` written for LLMs/automated
clients, an MLCommons **Croissant** JSON-LD document, schema.org markup,
`llms.txt` at the root, and the OpenAPI contract. Chapter 7 walks the agent
flow.

**(d) A human web entry point.** The same URLs answer browsers: the root is
a landing page listing datasets, the interactive demonstration viewers, and
the sample notebooks; each `/<store>.zarr/` renders a store page with
identity, citation, coverage and copy-paste open recipes, with the schema.org
graph embedded for search-engine and dataset-search indexing.

Content negotiation keeps these from colliding: browsers (Accept: text/html)
get pages, everything else gets JSON; `Accept: application/ld+json` on the
root returns the schema.org DataCatalog.

Two cross-cutting behaviours:

- **Host-based store gating** — deployment hostnames can be restricted to
  specific stores (e.g. a restricted store is only visible through its own
  hostname); hidden stores 404 everywhere else.
- **Live citation resolution** — collection/release DOIs are the durable
  fact; the proxy resolves the citation *text* live (crosscite.org in
  elsevier-harvard style for DOIs, the Carbon Portal's `citationString` for
  handle PIDs) with a daily stale-while-revalidate cache. Baked store strings
  are only fallbacks, so citations in catalog pages, Croissant `citeAs` and
  passports cannot go stale when a versioned DOI gets a new version.

## 3. The metadata model — what lives where

Everything a reader needs — identity, geography, citation, licence, QC rules,
access recipes — is *in or next to* the data, at the level where a reader
naturally encounters it:

| Layer | Where | What it holds | How to read it |
|---|---|---|---|
| Group attributes | `<store>/<GROUP>/.zattrs` | CF‑1.12/ACDD identity per station/site/cruise: `station_name`, `latitude`, `longitude`, `elevation`/`sampling_height`, `country`, `network`, per‑gas `*_source_doi` + `*_dobj_citation` (the object to cite), `*_obspack_citation`, `license` | `xr.open_zarr(...).attrs`, or the file directly |
| Root attributes | `<store>/.zattrs` | Store identity: `title`, `icos_domain`, `collection_doi` + `collection_citation`, `gas_dois`, `combined_views`, time/spatial coverage, and the machine `agent_guide` dict | `GET /<store>.zarr/.zattrs` |
| Consolidated metadata | `.zmetadata` at root **and per group** | Everything above plus every array's shape/chunks/dtype, in one document | implicit via `consolidated=True` |
| Combined views | top-level panels (`co2`, `ch4`, … for ObsPack; `_combined/<agg>` for FLUXNET; `_obs` flat tables for ocean) | The cross-entity form: dims `(station, time)` or a flat obs table, with station metadata (`latitude`, `longitude`, `sampling_height`, `citation`, `source_doi`) as arrays on the `station` dimension | `xr.open_zarr(url + "/co2")` — see notebook 08 |
| Variable catalogue | `GET /variables`, `/variables/{id}` | One entry per queryable variable: id (`<store-stem>.<group>.<shortname>`, `/`→`-` in groups), unit, long name, QC companion, coords, query kind | JSON; drives `/query` |
| Croissant sidecar | `GET /<store>.zarr/croissant` | MLCommons Croissant JSON-LD: dataset identity, `citeAs` (live-resolved), licence, distribution | JSON-LD |
| Agent guide | `GET /<store>.zarr/agent_guide` (also embedded in root attrs) | Machine recipe: how to open, layout, coords, the QC **keep rule**, query API pointers | JSON |
| Data passports | `/query` response tail / Arrow schema metadata; `GET /<store>.zarr/session/passport` | RO-Crate JSON-LD record of an access: what, when, how many bytes, citation, licence, sha-256 | see 5.6 |

**Finding stations** — three idioms, by increasing weight:

1. *You know the id*: it is the group name. Atmosphere ids are
   trigram + intake height (`CBW207`); FLUXNET sites are `SE-Htm`-style with
   an aggregation subgroup; SOCAT cruises are expocodes (`34FM20240623`,
   named by cruise *start*).
2. *Select by geography/height*: open a combined panel lazily and filter on
   its `latitude`/`longitude`/`sampling_height` coords (notebook 08), or let
   `/query` do it with `lat_min…`/`height_min…`.
3. *Full inventory*: open the **root** consolidated metadata once (~16 MB for
   icos-obspack — deliberately the expensive document) and sweep every
   group's attributes in one request (notebook 09). For a single series,
   never open the root — open the group URL.

## 4. Using it efficiently — xarray and REST

The five habits, in the order the notebooks teach them:

1. **Open the group URL, not the store root.**
   `xr.open_zarr("https://zarr.icos-cp.eu/icos-obspack.zarr/CBW207", consolidated=True)`
   fetches ~0.2 MB of metadata; the root document is ~16 MB. Seconds versus
   instant, on every open.
2. **Slice before you load.** Everything is lazy until `.load()`/`.values`;
   a `.sel()` window fetches only the covering chunks (2,232 of 296,266
   samples in under a second — notebook 02). This is equally what makes the
   1°×1° global SOCAT cube browsable: one month-map or one box's time series
   are each a few chunks (notebook 09).
3. **Cross-station questions go to the combined views.** One lazy `.sel` on
   the `(station, time)` panel replaces a loop over groups, and the station
   coords make it queryable by geography (notebook 08).
4. **Filtered extracts go to REST.** When the answer is "a table under these
   filters" — bbox, height window, time range, QC — one `/query` URL beats
   client-side assembly, arrives with a passport, and needs only `requests` +
   `pandas`. Use `format=arrow` beyond a station-year: ~10× smaller than
   ndjson and milliseconds to parse (a full 227k-row station record in
   ~0.6 s).
5. **Apply the store's QC rule** — or let `apply_qc=true` do it server-side
   (identical result, see below):

   | Store | Flag | Keep |
   |---|---|---|
   | icos-obspack | `<gas>_qc_flag` (letter) | first character `O` or `U` |
   | noaa-obspack | `<gas>_qc` (uint8 use-flag) | `== 0` |
   | icos-socat / socat | `<var>_QC` (WOCE) | `== 2` (‑1 = no source flag) |
   | FLUXNET hourly root | `<var>_QC` (int) | `<= 1` |
   | FLUXNET aggregated dd/ww/mm/yy | `<var>_QC` (fraction) | `> 0.3` — and GPP/RECO carry **no QC of their own** (they are partitioned from NEE): mask them with `NEE_QC` |

   These rules live in one place in the code (`icos_zarr.qc`) and are what
   the REST engine, the viewers and the agent guides all derive from.

Use **zarr-python ≥ 3** as the client (it reads the stores' v2 format
natively, opens plain URLs without fsspec, and **raises on failed chunk
fetches**). The caveat for anyone pinned to zarr-python 2: that version
silently fill-values any chunk whose fetch fails (`on_error="omit"` in its
fsspec store), so on a slow or lossy connection timed-out chunks masquerade
as NaN gaps — cap the concurrency there with
`fsspec.config.conf["gather_batch_size"] = 16`.

Typical costs (measured from a domestic connection; the VM-local weekly check
runs the same notebooks ~10× faster): group open + full 30-year series ~1.2 s
warm (~4 s first touch), portal-object binary column read ~0.4 s, REST year
extract ~0.4 s, OPeNDAP ~6 s handshake before the first byte — which is why
OPeNDAP is reserved for multi-GB gridded netCDF (notebook 06).

## 5. The REST interface

### 5.1 Discovery

| Endpoint | Returns |
|---|---|
| `GET /` | store list + root agent guide (JSON); DataCatalog with `Accept: application/ld+json`; landing page for browsers |
| `GET /llms.txt` | plain-text service self-description (llmstxt.org convention) |
| `GET /openapi.json` | the machine contract for everything below |
| `GET /variables` | the variable catalogue (filterable by store/domain) |
| `GET /variables/{id}` | one catalogue entry |
| `GET /<store>.zarr/` | store landing page / JSON summary |
| `GET /<store>.zarr/agent_guide` | the store's machine access guide |
| `GET /<store>.zarr/croissant` | MLCommons Croissant JSON-LD |
| `GET /version` | deployed git build + build time |

### 5.2 `GET /query` — filtered extracts

Required: `id` (a catalogue id, e.g. `icos-obspack.co2.co2`). Filters:

| Parameter | Meaning |
|---|---|
| `station` | comma-separated station ids, **case-sensitive** (ecosystem sites are mixed-case: `SE-Htm`). Panel stores: group ids (`CBW207,HTM150`) — the direct alternative to bbox + height. Obs-table stores with a station/platform table (icos-socat): line ids like `DE-SOOP-Finnmaid`, selecting all of that platform's cruises. Unknown ids → 400 naming a near-miss casing |
| `cruise` | comma-separated cruise expocodes (`34FM20240623`), obs-table stores, case-sensitive; ANDs with `station` when both given. Unknown ids → 400 |
| `lat_min` `lat_max` `lon_min` `lon_max` | bounding box |
| `height_min` `height_max` | sampling-height window (tall towers; station-panel stores) |
| `start` `end` | ISO time window; **`end` is exclusive** on every store |
| `apply_qc=true` | **drop** rows failing the store's recommended QC rule (table in ch. 4) — the result matches the store-route recipe row for row |
| `qc_max` | numeric-threshold variant (drops rows with flag > threshold) |
| `source_doi_prefix` | keep obs whose cruise's source DOI starts with the prefix (e.g. `10.18160` = ICOS platforms; obs-table stores) |
| `reduce` + `pos_tol`, `val_tol` | server-side per-cruise map thinning (obs-table): `track` = Douglas-Peucker, `stride`, `grid` |
| `max_rows` | row cap (down-sampled, not truncated, under `reduce`) |
| `format` | `ndjson` (default, gzip-negotiated), `arrow` (zstd IPC stream), `parquet`, `csv` (plain text). Any other value → 400 |

Responses: ndjson streams one JSON object per row, with the **data passport
as the final line** (`{"_passport": …}`); Arrow/Parquet carry the identical
passport in the schema metadata under `data_passport`. CSV is the exception:
it has nowhere to put metadata, and a passport is ~7 KB even for two rows —
past what an HTTP header block can hold — so a CSV response carries only
`X-Data-Citation`, `X-Data-License` and `X-Data-DOI` headers, and the body is
pure data that loads with a bare `read.csv()`/`pd.read_csv()`. **If you need
the provenance, ask for `parquet` or `ndjson`.**

**Errors are loud by design.** A filter that cannot apply to the variable —
a height window on an ocean obs-table, an unknown station id — is an HTTP
400 *naming the parameter and the reason*, never a silently ignored filter or
an empty 200. Treat a 400 as "wrong recipe", read the message, do not retry
the same URL.

### 5.3 `GET /summary`

Same filters, no rows: returns `n_obs`/`n_cells`, `n_cruises`, the lat/lon/
time extent of the selection and an `est_bytes` — "how big is my selection"
before you download it.

### 5.4 Query kinds

Each catalogue entry has a `query_kind` deciding which filters apply:
`station_time` (dense station panels — atmosphere, FLUXNET combined),
`obs_table` (flat observation tables — SOCAT `_obs`, 44M-row global SOCAT),
`grid` (lat×lon×time cubes — socat-gridded).

### 5.5 Sessions

Direct Zarr reads are grouped into per-client, per-store sessions closed by
~5 min of inactivity or explicitly:

| Endpoint | Behaviour |
|---|---|
| `GET /<store>.zarr/session/passport` | **closes** the open session and mints its passport immediately ("asking for the passport means I'm done"); a closed session's passport stays retrievable for an hour |
| `POST /<store>.zarr/session/close` | close without retrieving |

### 5.6 Data passports

Every access route yields an **RO-Crate JSON-LD passport**: the exact query
or the accessed groups/arrays, row/byte counts, access date, the citation
(live-resolved), licence, the stations/data objects touched with their PIDs,
and a self-certifying `passportSha256` (null the field, canonicalise,
re-hash — notebook 07 verifies one). Passports are the reproducibility
mechanism for **live** datasets: they pin *which slice* of *which release*
was read *when*.

### 5.7 Admin

`POST /admin/rescan`, `GET /admin/log`, and write operations on `/variables`
(`POST`/`PUT`/`DELETE`) require the admin token; `GET /variables/suggest`
proposes catalogue entries from a store's structure.

## 6. The sample notebooks

Fourteen notebooks in [`notebooks/`](../notebooks/) — 01–09 teach one access
pattern each, 10–14 are advanced worked examples. Every cell is executed
against the live services before committing, and re-executed by a weekly cron
on the VM that e-mails only when one breaks:

| # | Teaches |
|---|---|
| [01](../notebooks/01_portal_objects_icoscp.ipynb) | The **citable route**: `icoscp_core` discovery, citations, reading the portal's typed binary column store (one call for all four Cabauw intake heights) |
| [02](../notebooks/02_atmosphere_co2_quickstart.ipynb) | The Zarr **quickstart habits**: group-URL open, letter-flag QC, lazy slicing, the on-demand session passport |
| [03](../notebooks/03_rest_query_and_passports.ipynb) | The **REST route**: `station=` selection, bbox/height/time filters, the passport in the ndjson tail, Arrow bulk |
| [04](../notebooks/04_ecosystem_fluxes.ipynb) | **FLUXNET**: aggregation groups, the NEE/GPP/RECO reference-slice cubes, fraction QC |
| [05](../notebooks/05_ocean_socat.ipynb) | **Ocean**: SOCAT ship tracks with `reduce=track`, the station coverage Gantt, a one-station year map via `station=`, WOCE QC |
| [06](../notebooks/06_opendap_gridded.ipynb) | **OPeNDAP** for multi-GB gridded netCDF — and when *not* to use it |
| [07](../notebooks/07_reproducibility.ipynb) | **Reproducibility**: passports on all three routes, hash verification, the results-folder checklist |
| [08](../notebooks/08_combined_views.ipynb) | **Combined views**: stations by geography, a dask select→aggregate→`.compute()` latitude transect, ranking all FLUXNET sites in one expression |
| [09](../notebooks/09_zarr_under_the_hood.ipynb) | **Under the hood**: zarr-python directly (chunks, codecs, store anatomy), the one-request whole-store inventory, the gridded cube |
| [10](../notebooks/10_north_sea_bloom.ipynb) | **North Sea blooms** (advanced): the Thornton Buoy record, thermal vs biological pCO₂, bloom detection, air–sea CO₂ flux with ERA-5 winds (needs a free DestinE EarthDataHub token) |
| [11](../notebooks/11_explore_zarr.ipynb) | **Site explorer** (advanced): one FLUXNET site end to end — every aggregation group, the provenance record, 4-D METEOSENS profiles, full variable inventory |
| [12](../notebooks/12_nl_2024_cross_domain.ipynb) | **Cross-domain extraction** (advanced): one bbox + year across atmosphere CO₂, ecosystem NEE and ocean fCO₂ — one xarray expression each, a passport per store |
| [13](../notebooks/13_socat_v2026_tour.ipynb) | **Global SOCAT tour** (advanced): the 44M-obs synthesis — cruises, one ship's fleet history, the gridded fCO₂ globe, the 25-year regional trend gridded vs cruises |
| [14](../notebooks/14_explore_obspack.ipynb) | **ObsPack network explorer** (advanced): station index from consolidated metadata, the coverage Gantt for every station × gas, the network map |

Standalone scripts live in [`examples/`](../examples/) — currently the ICOS
Class 1/2 monthly-statistics exporter (importable + CLI, csv/pyarrow/netcdf/
parquet).

## 7. AI agents and the ICOS Zarr service

The service treats automated agents as first-class users; the design goal is
that **an agent given nothing but the base URL can discover, read, cite and
document its access without human help**:

1. `GET /` (or `/llms.txt`) — what this service is, which stores exist,
   where each store's guide lives.
2. `GET /<store>.zarr/agent_guide` — the store's machine recipe, written for
   an LLM audience: the exact `open_zarr` call, the layout (`station × time
   panel`, coords), the **QC keep rule as an executable sentence**, the
   identity attributes, and the query API pointer.
3. `GET /variables` → `GET /query?...` — no Zarr tooling needed; ndjson or
   Arrow with the passport attached.
4. Keep the passport. The agent's provenance obligation is discharged by
   storing the JSON-LD passport next to its results — access date, slice,
   citation and integrity hash included.

Design choices that specifically serve agents:

- **Fail-loud parameter validation** (ch. 5.2): a 400 with a prose reason is
  something an LLM can read and correct; a silently dropped filter is a
  wrong answer it will confidently report.
- **One QC truth**: the keep rules in the guides, the `apply_qc`
  implementation and the notebook recipes derive from the same module, so an
  agent following any of them gets the same numbers.
- **Croissant + schema.org**: dataset-search and ML-catalog tooling can
  ingest the stores without ICOS-specific code.
- **Citations resolve live** (ch. 2): an agent quoting the `citation` field
  gets the current text for the DOI, not whatever was baked at build time.
- The interactive viewers emit **copy-paste code snippets** reproducing the
  displayed selection — the same recipes the guides teach.

Practical limits: `max_rows` caps a single `/query` (use `format=arrow` and
paginate by time window for bulk); heavy sweeps should prefer one root
`.zmetadata` fetch over per-group polling; sessions are per client IP — a
fleet of workers behind one NAT shares one passport.
