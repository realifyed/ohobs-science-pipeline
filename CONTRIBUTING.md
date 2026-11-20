# Contributing

Create a virtual environment and run `python -m pip install -e ".[dev,diagnostics]" -e ./packages/osp-sim`.
Run `ruff check src packages/osp-sim/src tests benchmarks scripts`,
`ruff format --check src packages/osp-sim/src tests benchmarks scripts`,
`mypy src packages/osp-sim/src`, and `python -m pytest`. Include a test and reference for
scientific algorithm or metadata changes. Use synthetic FITS for routine tests.
Confirm permissions and remove private metadata before sharing observations.
See the [development and migration guide](docs/installation/SIMULATION-MIGRATION.md)
for Core-only tests and the provenance contract.
In a pull request, describe changed product semantics, actual test evidence,
known limitations, and any migration. A reviewer should check the numerical
assumptions and follow the reproduction command before accepting an algorithm change.

## Source and data review

Review staged files with `git diff --cached` before committing. Keep raw
observations, private commissioning inventories and generated packages
outside version control. The release bundle contains synthetic examples
and summary evidence.

The optional local pre-commit configuration uses the Ruff version installed
in the project's development environment. Run `python -m pip install pre-commit`
and `pre-commit install` if you want the same checks before each commit.
Use `pre-commit run --all-files` for a full local check.
