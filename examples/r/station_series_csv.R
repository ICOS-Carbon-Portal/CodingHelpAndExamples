# One station's QC-passed CO2 series in R, with no extra packages needed for
# the data itself.
#
# Verified against the live service 2026-08-18 with R 4.3.3:
#   8701 rows, mean 426.837 ppm, only 'O' flags, no NAs.
#
# `format=csv` is what makes read.csv applicable. WITHOUT it the endpoint
# streams ndjson and read.csv parses that into seven junk columns instead of
# failing — a data frame that looks real and is not.

url <- paste0("https://zarr.icos-cp.eu/query?id=icos-obspack.co2.co2",
              "&station=CBW207&start=2023-01-01&end=2024-01-01",
              "&apply_qc=true&format=csv")

df <- read.csv(url)
df$time_co2 <- as.POSIXct(df$time_co2, tz = "UTC")   # the CSV times are UTC

cat("rows:", nrow(df), "cols:", ncol(df), "\n")
cat("time range:", format(min(df$time_co2)), "->", format(max(df$time_co2)), "\n")
cat("mean co2:", round(mean(df$co2), 3), "ppm\n")
cat("qc flags kept:", paste(unique(df$co2_qc_flag), collapse = ","), "\n")

# CSV cannot carry the data passport, so the citation travels in response
# headers. Reading those needs one GET whose headers you keep — `curlGetHeaders`
# will NOT do, because it issues HEAD and this endpoint answers 405 to that.
if (requireNamespace("curl", quietly = TRUE)) {
    r <- curl::curl_fetch_memory(url)
    h <- curl::parse_headers(r$headers)
    cat("\n", grep("^x-data-citation", h, value = TRUE, ignore.case = TRUE), "\n", sep = "")
    cat(grep("^x-data-doi", h, value = TRUE, ignore.case = TRUE), "\n", sep = "")
}

# For work you intend to publish, prefer station_series_arrow.R: it carries the
# full RO-Crate passport, not just the citation line.
