# Public Python workflows

Core provides the reduction APIs below. The example obtains data through the
optional Simulation package. Real workflows use existing raw inputs and an
observational configuration.

```python
from pathlib import Path

from ohobs_pipeline.config import load_config
from ohobs_pipeline.masters import build_master
from ohobs_pipeline.pipeline import reduce_exposure
from ohobs_pipeline.products import read_calibrated
from ohobs_pipeline.reporting import exposure_report
from ohobs_sim.generator import Simulation, generate_dataset

root = Path("sim-session")
generate_dataset(root, Simulation.model_validate({"seed": 1234, "lights": 1}))
config = load_config(root / "simulation.yaml")
dark = build_master(sorted((root / "dark").glob("*.fits")), config)
short = build_master(sorted((root / "flat_dark").glob("*.fits")), config)
flat = build_master(sorted((root / "flat").glob("*.fits")), config, flat_dark_id=short.id)
receipt = reduce_exposure(root / "light/light-00000.fits", config, dark_id=dark.id, flat_id=flat.id)
product = Path(receipt["path"])
data = read_calibrated(product)
report = exposure_report(product)
print(data.science.shape, report["state"])
```

`Calibrated.variance` is variance. The on-disk ERR extension is its square
root. DQ combines integer bit flags. Use `jobs.create_job` and `jobs.run_job`
for persistent batch processing. `astrometry.solve` accepts source
candidates, shape, observation time, backend configuration, and a diagnostics
directory. It returns a WCS and a separate verification report. Online
authorization is explicit and the credential is process-scoped.
