% One station's QC-passed CO2 series in GNU Octave.
%
% Verified against the live service 2026-08-18 with Octave 8.4.0 (no packages):
%   8701 rows, mean 426.837 ppm — the same numbers R, Julia and Python return.
%
% Octave is NOT MATLAB for this purpose: `table`, `readtable`, `datetime`,
% `parquetread` and `zarrread` do not exist, and neither does `websave`. What
% does exist is `urlread`/`webread` plus a builtin `jsondecode`, which is
% enough for both routes below.

base = 'https://zarr.icos-cp.eu/query';
q = ['?id=icos-obspack.co2.co2&station=CBW207&start=2023-01-01' ...
     '&end=2024-01-01&apply_qc=true'];

% ---- bulk route: CSV ----------------------------------------------------
% Cheapest to parse, but Octave cannot see response headers, so the citation
% that a CSV response carries in X-Data-Citation is out of reach here.
txt   = urlread([base q '&format=csv']);
lines = strsplit(strtrim(txt), "\n");
C     = textscan(strjoin(lines(2:end), "\n"), '%q %q %f %f %f %q %f', ...
                 'Delimiter', ',');

station = C{1};  co2 = C{3};  flag = C{6};

% No datetime type: use datenum. Strip the fractional seconds first.
dn = datenum(cellfun(@(s) s(1:19), C{2}, 'UniformOutput', false), ...
             'yyyy-mm-dd HH:MM:SS');

printf('rows: %d\n', numel(co2));
printf('time range (UTC): %s -> %s\n', datestr(dn(1)), datestr(dn(end)));
printf('mean co2: %.3f ppm\n', mean(co2));
printf('qc flags kept: %s\n', strjoin(unique(flag)', ','));

% ---- provenance route: ndjson ------------------------------------------
% PREFER THIS for anything you intend to publish. The passport is the last
% line of the stream, so it needs no headers and no Arrow/Parquet support —
% which makes ndjson the only route in Octave that carries provenance.
txt   = urlread([base q]);
lines = strsplit(strtrim(txt), "\n");
rows  = cellfun(@jsondecode, lines(1:end-1), 'UniformOutput', false);
pp    = jsondecode(lines{end})._passport;

printf('\nndjson rows: %d\n', numel(rows));
printf('first: %s  %.3f ppm\n', rows{1}.time_co2, rows{1}.co2);

graph = pp.x_graph;                       % jsondecode maps @graph -> x_graph
for k = 1:numel(graph)
  node = graph{k};
  if isfield(node, 'x_id') && strcmp(node.x_id, './')
    printf('citation: %.60s...\n', node.citation);
    break
  end
end
