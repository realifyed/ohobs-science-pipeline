# OSP Core and Simulation migration

The repository keeps Core at its original root and publishes `ohobs-science-pipeline`
from `src/ohobs_pipeline`. The optional package lives in `packages/osp-sim`.
Scientific tests and independent reference experiments live in `tests` and
`benchmarks`. Core processing has no Simulation dependency.

| Through a6 and rc1 | Starting with rc2 |
| --- | --- |
| `osp simulate generate --profile standard --output demo` | Install `ohobs-science-sim` and run `osp-sim generate --profile standard --output demo`. |
| `ohobs_pipeline.simulation` | `ohobs_sim.generator` exports `Simulation` and `generate_dataset`. |
| Old simulated data and masters | Regenerate with the new toolkit and rebuild in a fresh synthetic workspace. Files lacking required origin evidence are quarantined. |
| Observational workflows | Continue using `osp reduce`, `osp batch` and the existing public Core APIs. Older real masters can be reused when their original headers and source digests are present and observational. |

## Validate a source checkout

```sh
python -m pip install -e ".[dev,diagnostics,benchmark]" -e ./packages/osp-sim
python -m pytest -ra
python benchmarks/validate_simulation.py NEW_TRUTH_RUN
python benchmarks/commission_reference.py NEW_REFERENCE_RUN
python benchmarks/uncertainty_commission.py
python -m build --outdir dist
python -m build packages/osp-sim --outdir dist
python scripts/check_wheel.py CORE_WHEEL NEW_CORE_ENV
python scripts/check_wheel.py CORE_WHEEL NEW_COMBINED_ENV --sim-wheel SIM_WHEEL
```

Run `python -m pytest --ignore=tests/simulation` for the Core-only test set.
Core wheel and source distribution are versioned separately from their installation
environment. The supplied versions of both distributions can be installed together
from local wheels.

## Data origin policy

Each simulated FITS exposure has boolean `SIMULATE=T`, `ORIGIN='OSP Synthetic Generator'`,
`SIMGEN`, and `SIMVER`. The generator records its identity, version, parameters
and file SHA-256 digests in a manifest. The deliberately truncated adversarial fixture
contains the same origin declaration but is invalid FITS by design.

The generated configuration sets `synthetic_test: true`. An observational
configuration expects unmarked observational inputs. A test configuration
expects marked synthetic inputs throughout. Core checks calibration inputs
and flat correction lineage, and rejects a mixed-origin batch before
dispatch. Partial and contradictory origin cards are quarantined. The
policy uses no filename convention. For compatibility with observatory FITS,
the absence of simulation markers is treated as observational when there
are no synthetic indicators. Editable headers and checksums do not
authenticate the physical origin. Keep raw data, masters, and work areas
separate and retain acquisition and generation records.
