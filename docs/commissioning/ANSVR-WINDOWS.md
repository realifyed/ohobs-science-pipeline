# Commission ANSVR on Windows

OSP can call the Astrometry.net executable bundled with ANSVR 0.22. This backend
uses local Cygwin paths and passes only the fitting subset of candidate centroids
to the solver. The HTTP service can stay stopped. N.I.N.A. can keep its existing
acquisition and plate-solving configuration. The [ANSVR developer notes](https://gist.github.com/agalasso/684419e13a00dedd5312d46009482564)
describe direct invocation.

Use an ordinary PowerShell session on the Windows account where ANSVR is installed.
Install the OSP wheel using `python -m pip install PATH_TO_WHEEL`. Locate the
actual Cygwin tree and verify the bundled programs.

```powershell
$root = Join-Path $env:LOCALAPPDATA 'cygwin_ansvr'
Test-Path -LiteralPath "$root\bin\bash.exe"
Test-Path -LiteralPath "$root\bin\cygpath.exe"
& "$root\bin\bash.exe" --version
& "$root\bin\cygpath.exe" -u -- ((Get-Location).Path)
Get-ChildItem -LiteralPath "$root\usr\share\astrometry\data" -Filter 'index-*.fits' -File
```

Copy the example YAML and replace the astrometry block with the following.
Use the observed absolute path with forward slashes. Use the ANSVR backend
configuration for its configured index location. If the installation runs on
a separate Windows account, run these commands while signed in to that account.

```yaml
astrometry:
  backend: ansvr
  ansvr_root: PATH_TO_CYGWIN_ANSVR
  backend_config: PATH_TO_CYGWIN_ANSVR/etc/astrometry/backend.cfg
  timeout_s: 120
  index_manifest: ansvr-index-sha256.txt
```

Make the manifest next to the YAML. List the indexes the configured backend
actually searches. The example assumes the default directory. Keep the indexes
and manifest fixed during a run. OSP records the manifest digest. Generate a new
manifest whenever the index set changes.

```powershell
Get-ChildItem -LiteralPath "$root\usr\share\astrometry\data" -Filter 'index-*.fits' -File |
  Sort-Object Name | Get-FileHash -Algorithm SHA256 |
  ForEach-Object { '{0}  {1}' -f $_.Hash.ToLower(), (Split-Path $_.Path -Leaf) } |
  Set-Content -Encoding utf8 configs/ansvr-index-sha256.txt
osp config validate --config configs/commissioning.yaml
osp astrometry probe --config configs/commissioning.yaml
osp astrometry diagnose-raw "PATH_TO_LIGHT.fits" --config configs/commissioning.yaml --output raw-ansvr-diagnostic
```

A launch probe exercises the executable startup. A raw diagnostic writes source
measurements, a candidate WCS when available, and a verification report. Use a
new output directory for each attempt. If source extraction returns too few
sources, try a known sharp, high-SNR star field to commission the backend before
re-evaluating the science exposure. For the supplied H-alpha diagnostic,
`quality.detection_smoothing_sigma_px: 3` and `quality.fit_radius: 12` with the
default detection threshold produced measurable candidates. These settings
require separate assessment on other fields. If Cygwin fails with WinError 623 or exit
`0xc0000142`, repeat the launch probe outside a restricted shell. If the same
failure occurs there, use a working ANSVR installation or native Astrometry.net
on Linux, with the same recorded index and catalogue selection. A missing index
or unsuitable quad scale needs a different remedy. Check the solver log and the
[index scale table](https://astrometry.net/doc/readme.html).

For independent Gaia DR3 verification, restrict the solver configuration to
indexes built from an independent catalogue, such as 4200-series 2MASS indexes.
Configure a field-covering Gaia ECSV, documented index independence, and an RMS
limit chosen for the science use. See the query and residual checks in
[real-data commissioning](REAL_DATA_ANALYSIS.md). Match darks and flat-darks
before running `osp reduce` and verify the resulting science product using
`osp validate`. Record match count, field coverage, pre- and post-clipping RMS,
outliers, residual patterns, scale, parity, and checksums for each field.
