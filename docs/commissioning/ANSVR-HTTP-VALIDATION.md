# ANSVR HTTP commissioning and validation

**IMPLEMENTED.** The `ansvr_http` backend logs in on a configured loopback
address, submits brightness-ordered one-based centroids from the fitting
subset, polls submission and job status, and downloads the FITS WCS. Requests
use the ANSVR 0.22 protocol verified against the installed service source.
The client needs neither Cygwin nor a proxy. The separate `ansvr` backend
still supports direct invocation. Keep the ANSVR service configuration and
index set fixed for a commissioning run.

**REAL-DATA VALIDATED within source extraction.** Seven real Lagoon exposures
were ranked, four O and three H-alpha. The selected 120-second O-filter
observation had 49 fitted candidates
and 17 possible held-out sources after the deterministic split. These are
image detections. Catalogue match counts require a real solve. The nominal
1.07 arcsec/pixel follows from 2.9 μm pixels and the 560 mm focal-length
card. The initial solving interval was 0.95–1.19 arcsec/pixel.

**FAILED in the development session.** Both a login-only probe and the
selected observation's live solve stopped at `POST /api/login` with
WinError 10013. No centroids reached the solver. The service settings
shortcut, installed script, and historic logs agree on port 8080. Those
logs record ANSVR 0.22 starting Astrometry.net 0.38 and accepting clients;
a second startup recorded Address already in use. That history cannot
establish which process is currently listening. The sandbox denied direct
socket access, listener enumeration through CIM, and Windows event/registry
inspection. Its LOCALAPPDATA is redirected.

Static PE inspection of the installed Bash, cygpath, cygwin1.dll, and solve-field
found x86 images. Bash and cygpath import the bundled cygwin1.dll. The installed
solver has the same dependency. Earlier direct launches returned WinError 623
or `0xc0000142`; the bundled objdump also returned WinError 623 in this session.
These codes identify a relocation or initialization failure. Static imports
and restricted-session evidence cannot identify the specific loader conflict.
No DLLs or system settings were changed. Live solver duration, center, plate
scale, orientation, fit correspondences and Gaia residuals are **BLOCKED**.

## Exact Windows commands

Open **Ansvr Settings** in the Start menu and confirm it loads in the observing
account. If it fails, consult **Watch Ansvr Log** before launching a second
instance. If no process owns the configured port, start the installed
**Start Ansvr** shortcut. Do not stop an unknown listener. Use ordinary
PowerShell 7 with the normal account. Set the absolute paths if the kit and
workspace are in different directories.

```powershell
python -m pip install .\ohobs_science_pipeline-0.1.0rc2-py3-none-any.whl
osp doctor
$raw = 'PATH_TO_LIGHT.fits'
.\scripts\Commission-Ansvr.ps1 -Observation $raw -Output ansvr-first
```

The script discovers the port from the observing account registry, recent ANSVR
startup logs, or the documented default. If the Settings shortcut uses a
different port, specify `-Port PORT_NUMBER`. On a successful solve it writes
`solve/candidate.wcs`, `solve/validation.json`, and `solve/http-0.json`.
The candidate receipt records duration, center, scale, orientation, parity
and fitting/held-out counts. `windows-diagnostics.json` records port evidence,
available component hashes, and before/after raw hashes. If startup fails,
return that report, the error log, and the relevant ANSVR startup and solver
log lines. The optional `-ProbeDirect` records a separate executable launch.

## Independent Gaia verification

Keep only independently derived indexes in the active server configuration,
such as the supplied 4200-series 2MASS indexes. Record the index manifest
and ANSVR configuration. Query Gaia DR3 covering the candidate's full
footprint, with margin for pointing error, and export a local ECSV with
`source_id, ra, dec, pmra, pmdec, ref_epoch`, plus `ruwe` and
`duplicated_source` if available. Use the query in
[real-data commissioning](REAL_DATA_ANALYSIS.md) with the actual solved
center. Preserve catalogue cuts, query, and release. OSP epoch-propagates
proper motion and matches detections excluded from the fit.

```powershell
$root = Join-Path $env:LOCALAPPDATA 'cygwin_ansvr'
Get-ChildItem "$root\usr\share\astrometry\data" -Filter 'index-42*.fits' -File |
  Sort-Object Name | Get-FileHash -Algorithm SHA256 |
  ForEach-Object { '{0}  {1}' -f $_.Hash.ToLower(), (Split-Path $_.Path -Leaf) } |
  Set-Content -Encoding utf8 ansvr-index-sha256.txt
$limit = [double](Read-Host 'Enter the selected science RMS limit in arcseconds')
.\scripts\Commission-Ansvr.ps1 -Observation $raw -Output ansvr-gaia `
  -GaiaCatalogue .\gaia.ecsv -IndexManifest .\ansvr-index-sha256.txt `
  -IndependenceEvidence 'Active ANSVR indexes: manifest-listed 2MASS 4200 series' `
  -MaxRmsArcsec $limit
```

Send the result receipt, residuals, checksum manifest and relevant solver
logs. A successful solve with no catalogue produces an UNVERIFIED WCS.
ANSVR's supported HTTP endpoints supply the WCS and job status. They do not
report individual in-fit star correspondences. OSP reports independent
matching counts, pre- and post-clipping RMS, median, outlier fraction, and
field coverage when verification runs.

[ANSVR official instructions](https://adgsoftware.com/ansvr/),
[developer notes](https://gist.github.com/agalasso/684419e13a00dedd5312d46009482564),
[index provenance](https://data.astrometry.net/), and
[Microsoft Windows error reference](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/).
