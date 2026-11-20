# Source, development and distribution installation

Core's pyproject.toml is at the repository root. The separate simulator lives
under packages/osp-sim. Source installation needs no bundled wheel.
Use the environment's Python throughout; in unactivated PowerShell replace
`python` with `.\.venv\Scripts\python.exe`.

Ordinary installation:

```sh
python -m pip install .
python -m pip check
```

Editable development installation:

```sh
python -m pip install -e ".[dev,diagnostics]" -e ./packages/osp-sim
python -m pytest -ra
```

Core-only development uses `python -m pip install -e ".[dev]"` and skips the
simulator modules. To install the optional simulator normally, use
`python -m pip install . ./packages/osp-sim`. Supplying both source paths avoids
depending on an unpublished Core release on a package index.

Build both distributions:

```sh
python -m pip install build twine
python -m build --outdir dist
python -m build packages/osp-sim --outdir dist
python -m twine check --strict "dist/*"
```

The default build produces an sdist and rebuilds a wheel from that sdist.
Isolated build environments may need network access. Keep dist free of stale
versions. Install a locally built Core wheel without fixing its version:

```sh
python -c "from pathlib import Path; import subprocess,sys; wheels=list(Path('dist').glob('ohobs_science_pipeline-*.whl')); assert len(wheels)==1, wheels; subprocess.run([sys.executable,'-m','pip','install',str(wheels[0])],check=True)"
```

Run `python scripts/check_wheel.py CORE_WHEEL scratch/core-check` in a source
checkout; add `--sim-wheel SIM_WHEEL` for combined verification. Destinations
must be new. These checks install dependencies and run a complete fixture
reduction. `--wheelhouse DIRECTORY` is an explicit offline replay option,
not the primary installation method. See [testing](../developer-guide/testing.md).

The same checker accepts a source directory or sdist in place of CORE_WHEEL:
`python scripts/check_wheel.py . scratch/source-check` verifies Core source
installation in a fresh environment with no simulator or plotting dependencies.
