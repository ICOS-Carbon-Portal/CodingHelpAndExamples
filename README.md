# ICOS — coding help and examples

Worked examples and reference documentation for accessing **ICOS Carbon
Portal** environmental data programmatically: atmosphere greenhouse gases,
ecosystem fluxes and surface-ocean carbon, served as cloud-native
[Zarr](https://zarr.dev/) at **<https://zarr.icos-cp.eu>** alongside a REST
query API, OPeNDAP and the classic citable data objects.

Everything here runs against the live services. All data are CC-BY-4.0 —
please cite (every route hands you the citation, and most hand you a
machine-readable *data passport* recording exactly what you read).

| Folder | What's in it |
|---|---|
| [`notebooks/`](notebooks/) | Fourteen Jupyter notebooks — one access pattern each (01–09) and five advanced worked studies (10–14). Committed **with executed outputs**, so you can read them on GitHub without running anything. |
| [`examples/`](examples/) | Standalone scripts you can import or run from the command line. |
| [`docs/`](docs/) | The service reference and a walk-through tutorial. |

## Start here

- **New to the service?** [`docs/users_tutorial.md`](docs/users_tutorial.md)
  walks the four access routes end to end and compares them on the same
  question.
- **Want to look something up?**
  [`docs/zarr-proxy-reference.md`](docs/zarr-proxy-reference.md) is the
  canonical reference: what the service is, where every kind of metadata
  lives, the full REST parameter set, QC keep-rules per domain, and how AI
  agents can discover it all.
- **Prefer to read code?** Start with
  [`notebooks/02_atmosphere_co2_quickstart.ipynb`](notebooks/02_atmosphere_co2_quickstart.ipynb)
  (a station's CO₂ series in five cells) or
  [`notebooks/03_rest_query_and_passports.ipynb`](notebooks/03_rest_query_and_passports.ipynb)
  (one URL → a DataFrame, no Zarr tooling needed).

## Requirements

```
pip install xarray "zarr>=3" dask requests pandas matplotlib cartopy pyarrow pydap icoscp_core
```

Notebooks 02–05 and 07–09 and 11–14 need no account. Notebook 01's data cells
and notebook 06 (OPeNDAP) need a free
[Carbon Portal account](https://cpauth.icos-cp.eu/); notebook 10's air–sea
flux section additionally needs a free
[DestinE EarthDataHub](https://earthdatahub.destine.eu/) token.

## Other languages

The service is plain HTTP — Zarr over HTTPS plus a REST API — so it is not
Python-only. See [`docs/julia-and-r-plan.md`](docs/julia-and-r-plan.md) for
what Julia and R users can do today and what we plan to add.

## Keeping this honest

The notebooks are re-executed against the live services by a weekly job; if
one breaks, we hear about it. If you find something that does not work, or a
recipe you wish existed, please open an issue.
