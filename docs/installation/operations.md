# OSP processing diagnostics and recovery

Install the optional plotting dependencies with `python -m pip install ".[diagnostics]"`.
For an isolated release check from a source checkout, run these commands
with a candidate wheel path and a fresh destination.

```powershell
python scripts/check_wheel.py PATH_TO_WHEEL fresh-check
python scripts/check_wheel.py PATH_TO_WHEEL fresh-full-check --sim-wheel SIM_WHEEL
```

Use `--wheelhouse DIRECTORY` with the Python entry point for an offline
dependency installation. Point it at locally available distribution wheels
for the target Python and platform.

## Gaia catalogue access

```yaml
astrometry:
  gaia:
    enabled: true
    allow_network: true
```

A local ECSV supplied via `astrometry.catalogue` takes precedence. With
automatic retrieval enabled, cache hits are offline and verified by their
digest and query identity. Network misses send only the field parameters
and selection criteria to ESA. This requires an explicit network opt-in.
`python scripts/test_gaia_live.py NEW_CACHE` tests TAP access and offline
cache reuse with a neutral public field and no astronomical image.

A missing or rejected catalogue leaves the WCS candidate unverified.
The separate verification command can revisit a stored candidate once a
reference is available. Use a fresh `--revision` to deliberately produce
a new reduction after changing available references or solver conditions.
The original product and checkpoint are retained for reproducibility.
A credible catalogue-independence record and held-out image detections
are still required for WCS acceptance.

## Processing logs and diagnostic plots

Each run writes its own JSON Lines file under `work_dir/events`. Join
batch and exposure logs by `job_id`, and inspect a single execution by
`run_id`. The validated input SHA-256 provides a stable observation
identity. Events record master IDs, worker outcomes, stages, UTC event
times, elapsed time and recovery counts. A crashed worker may have no
final child event. Look for its digest and final status in the dispatcher
log and persisted batch audit. Raw headers, environment variables,
credentials and free-form exception text are excluded from these logs.

```powershell
osp plots --product SCIENCE_FITS --master MASTER_ID --config CONFIG --output diagnostics
osp plots --product SCIENCE_FITS --reference REFERENCE_FITS --output calibration-diagnostics
osp plots --uncertainty UNCERTAINTY_JSON --benchmark PERFORMANCE_JSONL --output benchmark-diagnostics
```

Choose calibration references measured independently on the same grid
and expressed in the same units as SCI. The source and PSF charts summarize
detected and fitted objects. The astrometric plot uses individually
reported matches and residuals, including clipped outliers. The coverage
and performance plots require recorded benchmark files.

An interrupted batch can be inspected with `osp jobs inspect JOB_ID --config CONFIG`
and resumed with `osp jobs retry JOB_ID --config CONFIG`.
Retain the same workspace so completed checkpoints can be audited and
reused. Retry applies to failed work under the same processing definition.
The [CLI reference](../cli-reference.md) lists command options.
