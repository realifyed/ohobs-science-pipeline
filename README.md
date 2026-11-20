# OHOBS Science Pipeline

OHOBS Science Pipeline (OSP) is an open-source astronomical data-reduction
system developed for the Open Horizon Observatory initiative. It provides
calibrated FITS products, image-quality assessment, astrometric solutions,
and reproducible scientific processing for student-run observatories.

**Status:** `0.1.0rc2` is a software pre-release

## Features

- Matched dark and flat-dark calibration, master management, and an
  evidence-gated bias-only workflow.
- Per-pixel uncertainty and data-quality masks, source measurements, and
  image-quality reports.
- Local Astrometry.net or ANSVR, explicitly authorized Nova solving, and
  independent Gaia catalogue checks.
- Resumable batch processing, integrity checks, and product provenance.

## Install the pre-release

From the extracted release bundle, use a fresh Python 3.11 or newer environment:

```console
python -m venv .venv
```

In Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install ./ohobs_science_pipeline-0.1.0rc2-py3-none-any.whl
.\.venv\Scripts\osp.exe version
.\.venv\Scripts\osp.exe doctor
```

On Linux or macOS:

```sh
. .venv/bin/activate
python -m pip install ./ohobs_science_pipeline-0.1.0rc2-py3-none-any.whl
osp version
osp doctor
```

Calibration and QC run offline. Astrometry can use [local Astrometry.net and indexes](https://astrometry.net/doc/readme.html), [ANSVR on Windows](docs/commissioning/ANSVR-WINDOWS.md), or [authorized Nova submissions](docs/installation/ONLINE_ASTROMETRY.md).

The exact validated Windows/Python 3.14 runtime dependencies are recorded in
`configs/constraints-windows-py314.txt`. Use `python -m pip install -c
configs/constraints-windows-py314.txt .` to request that dependency set.

## Quick start

Copy [the example configuration](configs/ohobs-01.example.yaml) to
`configs/run.yaml` and review the detector settings and matching rules.
Use compatible darks for the science exposures and compatible flat-darks
for each set of flats. Use measured detector parameters where the
configuration calls for them.

```console
osp fits inspect "raw/light.fits" --config configs/run.yaml
osp masters build --config configs/run.yaml --kind DARK dark/d01.fits dark/d02.fits dark/d03.fits dark/d04.fits dark/d05.fits
osp masters build --config configs/run.yaml --kind FLAT_DARK fd/fd01.fits fd/fd02.fits fd/fd03.fits fd/fd04.fits fd/fd05.fits
osp masters build --config configs/run.yaml --flat-dark FLAT_DARK_ID flat/f01.fits flat/f02.fits flat/f03.fits flat/f04.fits flat/f05.fits
osp reduce "raw/light.fits" --config configs/run.yaml --dry-run
osp reduce "raw/light.fits" --config configs/run.yaml
osp batch --input raw --config configs/run.yaml
osp validate PATH_TO_SCIENCE_FITS
```

Use the returned master IDs. Pass `--dark` and `--flat` when compatible candidates are ambiguous. Build separate sets for different flat filters or exposure times. `osp calibrate` runs detector correction alone. `osp qc` remeasures an existing product. `osp astrometry solve` writes separate candidate WCS and diagnostics. `osp reduce --revision LABEL` publishes a deliberate reprocessing.

FITS products contain calibrated pixels in `SCI`, one-sigma marginal
uncertainty in `ERR`, and bit flags in `DQ`. OSP writes JSON provenance
and quality reports. ADU inputs without a measured gain have unavailable
uncertainties. Only verified WCS enters the science FITS.

## Python API

```python
from pathlib import Path
from ohobs_pipeline.products import read_calibrated, validate_product

path = Path("PATH_TO_SCIENCE_FITS")
print(validate_product(path))
image = read_calibrated(path)
print(image.science.shape, image.variance.shape, image.dq.shape)
```

## Documentation and contributing

- [CLI reference](docs/cli-reference.md), [configuration](docs/configuration.md),
  [Python API](docs/api/PUBLIC.md), and [operations and recovery](docs/installation/operations.md).
- [Release status](docs/validation/RELEASE_STATUS.md) and
  [scientific assumptions and limitations](docs/science/assumptions-and-limitations.md).
- [Synthetic quick start](docs/getting-started/SYNTHETIC.md) for the optional
  `ohobs-science-sim` validation toolkit. Use it in an isolated synthetic
  workspace.
- [Contributing](CONTRIBUTING.md), [security reporting](SECURITY.md), and
  [BSD-3-Clause license](LICENSE).
