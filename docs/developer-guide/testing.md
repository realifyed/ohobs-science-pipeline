# Testing and release checks

Use the [editable setup](development-setup.md), then run:

```sh
python -m pytest -ra
python -m ruff check src packages/osp-sim/src tests benchmarks scripts
python -m ruff format --check src packages/osp-sim/src tests benchmarks scripts
python -m mypy src packages/osp-sim/src
python scripts/check_docs.py
python -m build --outdir dist
python -m build packages/osp-sim --outdir dist
python -m twine check --strict "dist/*"
```

Core-only tests run with `python -m pytest --ignore=tests/simulation` in an
environment without ohobs_sim. The scientific marker selects numerical
validation; the full suite also contains scientific tests without that marker,
so run the complete suite for release verification. Never replace regressions
with merely matching a rewritten implementation.

Use scripts/check_wheel.py for independent Core-only and combined environments
as described in [distribution installation](../installation/from-source.md).
scripts/smoke_core.py exercises installed CLI reduction on a frozen fixture;
scripts/smoke_api.py exercises the combined known-truth Python workflow.
The latter deliberately injects a truth WCS and does not claim live solving.

CI targets Windows/Linux and Python 3.11–3.14, checks dependency isolation and
builds wheels from sdists. Ordinary pull requests require no private credentials.
Live Gaia, Nova and external solver commissioning are separate opt-in checks.
Record actual failures, skips, versions and unavailable platforms in the
[verification record](../validation/repository-improvements.md).

`python scripts/verify_repository.py --output scratch/verification.json` runs
the release checks, fresh wheel/source environments and installed workflows,
saving a transcript with repository and home paths redacted. It requires the
combined development installation and network access for isolated builds and
dependency resolution. Each run uses a new scratch directory.
Add --live-gaia to also fetch the neutral public Gaia field and replay its
cache offline. This is opt-in and does not upload observations or use Nova keys.
