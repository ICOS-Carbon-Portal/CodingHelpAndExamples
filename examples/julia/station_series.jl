# One station's QC-passed CO2 series in Julia, via the REST route.
#
# Verified against the live service 2026-08-18 with Julia 1.10.4:
#   8701 rows, mean 426.837 ppm — the same numbers R and Python return.
#
# Why REST rather than Zarr.jl: the QC flags are |S1 byte arrays whose
# fill_value is base64 per the Zarr v2 spec, and Zarr.jl tries to convert that
# string to a character. `zopen` reads a group's arrays eagerly, so one flag
# array fails the whole group — you can read the numeric arrays one at a time,
# but never the flags, so client-side QC is not possible. apply_qc=true lets
# the server do it.

using HTTP, JSON3, DataFrames, Dates

q = Dict("id" => "icos-obspack.co2.co2", "station" => "CBW207",
         "start" => "2023-01-01", "end" => "2024-01-01",
         "apply_qc" => "true", "max_rows" => "200000")

body  = String(HTTP.get("https://zarr.icos-cp.eu/query"; query=q).body)
lines = split(body, '\n'; keepempty=false)
rows  = [JSON3.read(l) for l in lines[1:end-1]]   # the last line is the passport

# Type the columns explicitly. Building the DataFrame straight from JSON3
# values gives an abstract `Real` column and timestamps left as `String`.
df = DataFrame(
    station = String[r.station for r in rows],
    time    = DateTime[DateTime(r.time_co2, dateformat"yyyy-mm-ddTHH:MM:SSZ") for r in rows],
    co2     = Float64[r.co2 for r in rows],
)

println("rows: ", nrow(df), "  types: ", eltype.(eachcol(df)))
println("time range (UTC): ", minimum(df.time), " -> ", maximum(df.time))  # end is EXCLUSIVE
println("mean co2: ", round(sum(df.co2) / nrow(df), digits=3), " ppm")

# Cite what you used — the passport is the last line of the stream.
pp   = JSON3.read(lines[end])._passport
root = first(filter(n -> get(n, "@id", "") == "./", pp["@graph"]))
println("citation: ", first(root["citation"], 60), "...")
println("license : ", root["license"]["@id"])
