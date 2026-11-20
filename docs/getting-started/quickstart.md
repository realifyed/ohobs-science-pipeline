# Offline Core-only quickstart

Install Core from the repository root using the [platform guides](../index.md).
With that environment's Python run:

```sh
python scripts/smoke_core.py scratch/first-reduction
```

The destination must be fresh. The script extracts the small frozen synthetic
fixture in examples/core-smoke-fixture.zip, verifies its manifest hashes,
builds dark, flat-dark and flat masters, reduces a light and validates FITS
extensions and provenance through the installed CLI. It also inspects metadata,
remeasures QC and writes an HTML report. The separate simulator must be absent
for this Core-only isolation check; use `--with-simulation` only for a combined
installation, which generates its own fixture.

This is a software demonstration, not detector commissioning. A PARTIAL result
is expected when external astrometry is unavailable. SCI/ERR/DQ are still
validated. Inspect the printed result and the fixture's osp-work directory.
For a step-by-step observational workflow see [first reduction](first-reduction.md).
