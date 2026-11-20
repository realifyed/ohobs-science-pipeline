# OSP Simulation

This optional toolkit creates deterministic astronomical FITS data and known
ground truth for validating the OHOBS Science Pipeline.

```sh
python -m pip install . ./packages/osp-sim
osp-sim generate --profile standard --seed 1234 --output demo
osp-sim generate --profile adversarial --output adversarial-demo
```

Run the install command from the repository root in an isolated environment.
No prebuilt wheel is required. Core installs without this toolkit; the simulator
depends on Core and has no additional science-library requirements.
Build its distributions with `python -m build packages/osp-sim --outdir dist`
from the repository root after installing the build tool. For wheel installation,
supply the locally built Core and Simulation wheels together to pip.
Python >=3.11 is the metadata requirement; current local verification uses
Windows CPython 3.14.7. Other interpreter/platform combinations remain CI targets.
Its Python API is `from ohobs_sim.generator import Simulation, generate_dataset`.

The generated configuration explicitly selects a synthetic test workflow.
The manifest inventories the generator identity, version and file digests.
Keep generated data and masters in a separate workspace from real observations.
The adversarial profile places deliberately faulty inputs under `faults/`.
