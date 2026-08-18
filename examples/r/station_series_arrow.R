# The same series via Arrow — the route to use for work you intend to publish,
# because it carries the full RO-Crate data passport, not just a citation line.
#
# Verified against the live service 2026-08-18 with R 4.3.3 and arrow 25.0.0:
#   8701 rows, mean 426.837 ppm, a 30-node passport graph.

library(httr2); library(arrow)

req <- request("https://zarr.icos-cp.eu/query") |>
  req_url_query(id = "icos-obspack.co2.co2", station = "CBW207",
                start = "2023-01-01", end = "2024-01-01",
                apply_qc = "true", max_rows = 200000, format = "arrow")

resp <- req_perform(req)
df   <- read_ipc_stream(resp_body_raw(resp))          # a tibble

# TIMEZONE TRAP: the POSIXct comes back with no `tzone`, so R prints it in the
# session's timezone. On a machine set to Europe/Berlin the first January
# timestamp displays as 01:30 where the data say 00:30 UTC — same instant, but
# an hour of silent skew in anything diurnal. Pin it:
attr(df$time_co2, "tzone") <- "UTC"

cat("rows:", nrow(df), "cols:", ncol(df), "\n")
cat("time range:", format(min(df$time_co2)), "->", format(max(df$time_co2)), "UTC\n")
cat("mean co2:", round(mean(df$co2), 3), "ppm\n")

# The passport rides in the Arrow schema metadata.
tbl <- read_ipc_stream(resp_body_raw(req_perform(req)), as_data_frame = FALSE)
pp  <- jsonlite::fromJSON(tbl$schema$metadata[["data_passport"]])
root <- pp[["@graph"]][pp[["@graph"]][["@id"]] == "./", ]

cat("passport nodes:", nrow(pp[["@graph"]]), "\n")
cat("citation:", substr(root$citation, 1, 60), "...\n")
