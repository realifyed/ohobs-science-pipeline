# OSP Simulation

This optional toolkit creates deterministic astronomical FITS data and known
ground truth for validating the OHOBS Science Pipeline.

```sh
python -m pip install --find-links . ./ohobs_science_sim-0.1.0rc2-py3-none-any.whl
osp-sim generate --profile standard --seed 1234 --output demo
osp-sim generate --profile adversarial --output adversarial-demo
```

Run the install command from the extracted bundle with both wheels present.
Install local builds together when working from a source checkout. The simulator
depends on OSP Core and has no additional science-library requirements.
Its Python API is `from ohobs_sim.generator import Simulation, generate_dataset`.

The generated configuration explicitly selects a synthetic test workflow.
The manifest inventories the generator identity, version and file digests.
Keep generated data and masters in a separate workspace from real observations.
The adversarial profile places deliberately faulty inputs under `faults/`.
