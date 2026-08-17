# Sample notebooks

Illustrative Jupyter notebooks for ICOS data access — the "watch this space"
promised on the landing page. Every cell is executed against the live services
before committing (outputs included), so what you read is what runs.

| Notebook | Route | Shows |
|---|---|---|
| [01_portal_objects_icoscp](01_portal_objects_icoscp.ipynb) | `icoscp_core` | The citable route: discover released data objects, fetch the citation (anonymous), read columns from the portal's typed binary store — one height in ~0.1 s, all four Cabauw intakes in one batch call |
| [02_atmosphere_co2_quickstart](02_atmosphere_co2_quickstart.ipynb) | Zarr | A tall-tower CO₂ series in five cells: group-URL open (fast), letter-flag QC, monthly means, citation, and the **on-demand session data passport** |
| [03_rest_query_and_passports](03_rest_query_and_passports.ipynb) | REST `/query` | station-id selection (`station=CBW207`; bbox + height window for spatial picks), the passport in the ndjson tail, `format=arrow` for bulk (full station record in ~1 s) |
| [04_ecosystem_fluxes](04_ecosystem_fluxes.ipynb) | Zarr | FLUXNET aggregations, the NEE/GPP/RECO reference-slice cubes, fraction-QC masking |
| [05_ocean_socat](05_ocean_socat.ipynb) | REST + Zarr | SOCAT ship tracks with `reduce=track` thinning, one cruise in full, WOCE QC |
| [06_opendap_gridded](06_opendap_gridded.ipynb) | OPeNDAP | Multi-GB gridded netCDF sliced server-side: one emission-sector map, one grid-cell time series — and when *not* to use DAP |
| [07_reproducibility](07_reproducibility.ipynb) | all | Passports on every route, verifying the integrity hash, Croissant identity for live stores, the results-folder checklist |
| [08_combined_views](08_combined_views.ipynb) | Zarr (xarray) | The dense cross-station panels: select stations by geography, a lazy latitude transect, ranking all 42 FLUXNET sites in one expression |
| [09_zarr_under_the_hood](09_zarr_under_the_hood.ipynb) | zarr direct | Store anatomy with zarr-python (chunks, codecs, consolidated metadata), a one-request whole-store inventory, lazy month-maps from the gridded SOCAT cube |
| [10_north_sea_bloom](10_north_sea_bloom.ipynb) | zarr direct + ERA-5 | **Advanced worked example**: North Sea spring blooms from SOCAT — cruise search, the Thornton Buoy record, thermal vs biological pCO₂, bloom detection, and air–sea CO₂ flux with ERA-5 winds |
| [11_explore_zarr](11_explore_zarr.ipynb) | Zarr (xarray) | **Advanced**: one site end to end — every aggregation group, the provenance record, 4-D METEOSENS profiles, a full variable inventory, the session passport |
| [12_nl_2024_cross_domain](12_nl_2024_cross_domain.ipynb) | Zarr (xarray) | **Advanced**: one bbox + year across all three domains — atmosphere CO₂, ecosystem NEE, ocean fCO₂ — each a single xarray expression, with a passport per store |
| [13_socat_v2026_tour](13_socat_v2026_tour.ipynb) | REST + Zarr + plotly | **Advanced**: the global SOCAT v2026 synthesis — single cruise, one ship's fleet history, gridded fCO₂ globe, North-Atlantic window maps, the 2000–2025 trend gridded vs cruises |
| [14_explore_obspack](14_explore_obspack.ipynb) | zarr direct | **Advanced**: the ObsPack network at a glance — station index from consolidated metadata, one picked series, the full coverage Gantt (station × gas), the station map |

Requirements: `pip install xarray "zarr>=3" dask requests pandas matplotlib cartopy pyarrow pydap icoscp_core`.
(zarr-python 3 reads the stores' v2 format natively and raises on failed
chunk fetches; on zarr-python 2 also install `fsspec aiohttp` and cap
`fsspec.config.conf["gather_batch_size"]` on slow links.)
Notebooks 02–05 and 07–09 need no account or token; notebook 01's data cells
and notebook 06 (OPeNDAP) need a free
[Carbon Portal account](https://cpauth.icos-cp.eu/); notebook 10's flux
section needs a free [DestinE EarthDataHub](https://earthdatahub.destine.eu/)
token. All data CC-BY-4.0.

Re-execute before committing changes:

    jupyter nbconvert --to notebook --execute --inplace [0-9]*.ipynb

A weekly cron on the zarr VM (`tools/check_notebooks.py`, Mondays 06:30 UTC)
re-executes all of them against the live services and e-mails only when one
fails — silence means they still run as committed.
