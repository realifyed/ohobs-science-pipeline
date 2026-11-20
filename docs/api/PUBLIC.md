# Public Python workflows

These are intended user-facing Core entry points in the release candidate.
The 0.x API may evolve; pin the version for reproducible research. Lower-level
helpers are implementation details unless documented here. There is no separate
top-level convenience facade. Python exceptions report failures; inspect stage
statuses even when a call returns successfully.

| Function | Inputs and result |
| --- | --- |
| config.load_config(path) | YAML Path -> validated Config; resolves configuration paths. |
| ingest.inspect_frame(path, config=None) | Raw FITS Path -> Frame with metadata, shape, timing and manifest(). |
| masters.build_master(paths, config, flat_dark_id=None, kind=None) | Homogeneous FITS Paths -> Master with id and manifest. |
| pipeline.reduce_exposure(path, config, ...) | Raw LIGHT -> receipt dictionary including id, path, state; dark_id/flat_id select references. |
| products.validate_product(path) | Science FITS -> validation dictionary; raises for integrity/structure failures. |
| products.read_calibrated(path) | Science FITS -> Calibrated with science, variance, dq, noise_status. |
| quality.measure(image, settings, saturation_known=False) | Calibrated and Quality -> (QC dictionary, Source list). |
| reporting.exposure_report(path) | Science FITS -> integrity-checked report including quality and astrometry. |
| astrometry.load_candidate(header, shape, settings) | Candidate FITS Header, (height,width), Astrometry -> geometrically validated WCS; not catalogue verification. |
| astrometry.assess_candidate(path, shape, sources, observation_time, settings, ...) | Candidate, held-out Source list, astropy Time and reference settings -> Solution(wcs, report). |

## Reproducible Core-only example

Run from the repository root with Core installed. This extracts the included
frozen synthetic fixture, not real observations; it does not need the simulator.
The destination must be new. `python scripts/smoke_public_api.py` executes this
exact block in a fresh temporary working directory during verification.

```python
from pathlib import Path
from zipfile import ZipFile

from astropy.io import fits
from ohobs_pipeline.astrometry import load_candidate
from ohobs_pipeline.config import load_config
from ohobs_pipeline.ingest import inspect_frame
from ohobs_pipeline.masters import build_master
from ohobs_pipeline.pipeline import reduce_exposure
from ohobs_pipeline.products import read_calibrated, validate_product
from ohobs_pipeline.quality import measure
from ohobs_pipeline.reporting import exposure_report

root = Path("scratch/public-api-example")
root.mkdir(parents=True, exist_ok=False)
with ZipFile("examples/core-smoke-fixture.zip") as archive:
    archive.extractall(root)
config = load_config(root / "simulation.yaml")
raw = root / "light/light-00000.fits"
frame = inspect_frame(raw, config)
assert frame.values["kind"] == "LIGHT"
dark = build_master(sorted((root / "dark").glob("*.fits")), config)
short = build_master(sorted((root / "flat_dark").glob("*.fits")), config)
flat = build_master(sorted((root / "flat").glob("*.fits")), config, flat_dark_id=short.id)
receipt = reduce_exposure(raw, config, dark_id=dark.id, flat_id=flat.id)
product = Path(receipt["path"])
print(validate_product(product))
image = read_calibrated(product)
qc, sources = measure(image, config.quality)
report = exposure_report(product)
assert image.science.shape == image.variance.shape == image.dq.shape
assert report["integrity"] == "VERIFIED"
candidate = load_candidate(fits.getheader(root / "truth.fits"), frame.shape, config.astrometry)
assert candidate.has_celestial
print(image.science.shape, qc["status"], len(sources), receipt["state"])
```

For observations, replace fixture extraction with existing raw data and a real
configuration. Do not enable synthetic_test for observations. Calibrated.variance
is variance; the on-disk ERR plane is its square root. QC remeasurement does not
alter the published report. Loading a WCS does not establish scientific validity.

The combined `scripts/smoke_api.py` workflow additionally generates known truth,
assesses a candidate against held-out sources, checks residuals and plots a
product with an injected truth WCS. It requires the simulator and diagnostics
extra; its injection is an offline test, not a live solver result. For persistent
batch APIs and operational details see [architecture and operations](../operations.md).
