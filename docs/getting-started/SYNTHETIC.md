# Reduce a synthetic observing session

Python 3.11 or later is required by package metadata. Local commissioning
used Windows and Python 3.14.7. The hosted Windows/Linux matrix is defined
and still awaits independent runs.

From the repository root in PowerShell, install both source packages and
generate a fresh dataset (no bundled wheels are required):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install . ./packages/osp-sim
$osp = '.\.venv\Scripts\osp.exe'
& $osp doctor
& '.\.venv\Scripts\osp-sim.exe' generate --profile standard --seed 1234 --output example --adversarial
$cfg = 'example/simulation.yaml'
$d = @(Get-ChildItem example/dark/*.fits | ForEach-Object FullName)
$fd = @(Get-ChildItem example/flat_dark/*.fits | ForEach-Object FullName)
$f = @(Get-ChildItem example/flat/*.fits | ForEach-Object FullName)
& $osp masters build --config $cfg --kind DARK @d
$short = & $osp masters build --config $cfg --kind FLAT_DARK @fd | ConvertFrom-Json
& $osp masters build --config $cfg --kind FLAT --flat-dark $short.id @f
$product = & $osp reduce example/light/light-00000.fits --config $cfg | ConvertFrom-Json
& $osp validate $product.path
& $osp report --product $product.path --html example/exposure.html
& $osp batch example/light --config $cfg
```

On Linux use `.venv/bin/osp` and `.venv/bin/osp-sim` and use shell
globs for each master input group. The synthetic
dataset is deliberately configured with an absent solver. Calibrated products
remain usable and report partial astrometric status.

The profiles are standard, high, low, zero, crowded and defects. Advanced
noise, gain, quantization, temperature response and nonlinearity parameters
are available through the Python API. Science truth is expected electrons
before pixel response. For comparison with the median-normalized SCI in ADU,
multiply truth by the normalization response and divide by gain. Positions in
truth ECSV are zero-based. The FITS WCS uses one-based reference pixels.
FITS origin headers, master lineage and the generated `synthetic_test: true`
configuration isolate the simulated calibration frames. A fixed seed and
the same dependency versions reproduce the data and checksums.

Use `--lights 1000` to generate a large fixture. Use
`python benchmarks/batch_commission.py --cases 1000:4` to test queueing and
resume on a provisioned host. Full resolution uses
`--shape 2180 3856`. Review disk capacity and the measured per-process memory
before selecting concurrency.
