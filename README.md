# OHOBS Science Pipeline

An open-source astronomical data-reduction pipeline for FITS calibration,
uncertainty propagation, image-quality assessment, and astrometric validation.
OSP originated at Open Horizon Observatory and can be configured for other
observatories and monochrome detectors. It performs scientific detector
correction rather than image stretching or artistic astrophotography processing.

## Status

**0.1.0rc2 is a scientific software pre-release.** Package metadata requires
Python 3.11 or later. Local verification used Windows with CPython 3.14.7.
See the [verification record](docs/validation/repository-improvements.md) for
platform coverage and [scientific limitations](docs/science/assumptions-and-limitations.md).

## Capabilities

- Strict FITS ingestion and explicit metadata normalization.
- Matched dark, flat-dark and flat masters; evidence-gated bias-only calibration.
- Marginal pixel uncertainties, DQ masks and immutable provenance.
- Source detection, PSF fitting, background and image-quality measurements.
- Native Astrometry.net, Windows ANSVR and authorized online Nova solving,
  with independent Gaia checks before accepting WCS.
- Persistent batch jobs, restart recovery, integrity checks, JSON and HTML reports.
- Command-line and Python interfaces; optional diagnostic plots.

## Install from source

Clone the repository and run installation commands from its root:

```sh
git clone https://github.com/realifyed/ohobs-science-pipeline.git
cd ohobs-science-pipeline
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\osp.exe --help
.\.venv\Scripts\osp.exe doctor
```

Linux Bash (execution pending):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
osp --help
osp doctor
```

Dependencies install through metadata. No bundled wheel or simulator is
required. See [Windows](docs/installation/WINDOWS.md), [Linux](docs/installation/linux.md),
[source and wheel installation](docs/installation/from-source.md) and
[troubleshooting](docs/installation/troubleshooting.md).

## Quick start and configuration

For an offline Core-only demonstration with included synthetic FITS, use the
environment's Python from the repository root:

```sh
python scripts/smoke_core.py scratch/first-reduction
```

This builds compatible masters, reduces a light and validates SCI/ERR/DQ and
provenance using the installed CLI. See the [quickstart](docs/getting-started/quickstart.md)
and [first observational reduction](docs/getting-started/first-reduction.md).

Copy [the generic configuration](configs/examples/observatory.yaml) to
`observatory.yaml` in the repository root, then adjust paths and policies:

```sh
osp config validate --config observatory.yaml
osp fits inspect observations/light.fits --config observatory.yaml
osp reduce observations/light.fits --config observatory.yaml --dry-run
```

Reduction requires matching masters. The [configuration guide](docs/user-guide/configuration.md)
explains measured detector parameters and metadata. A separate
[OHOBS-01 example](configs/examples/ohobs-01.yaml) describes one instrument.

## Scientific products

Products contain calibrated `SCI`, one-sigma marginal `ERR`, and bitwise `DQ`
extensions. Unknown ADU gain makes uncertainty unavailable. Covariance and
flat normalization uncertainty are not fully represented. Only independently
verified WCS enters science FITS; solver candidates remain diagnostic.
JSON provenance and stage reports preserve outcomes. See [data products](docs/user-guide/data-products.md).

## Documentation, simulation and contribution

Start at the [documentation index](docs/index.md), [CLI reference](docs/cli-reference.md)
or [Python API](docs/api/PUBLIC.md). Historical [validation](docs/validation/RELEASE_STATUS.md)
and [OHOBS commissioning](docs/commissioning/RELEASE_READINESS.md) remain separate.

The optional simulator is a separate distribution for known-truth validation,
regression tests and development examples:

```sh
python -m pip install . ./packages/osp-sim
osp-sim generate --profile standard --seed 1234 --output synthetic-demo
```

See the [synthetic tutorial](docs/getting-started/SYNTHETIC.md).
For development, install `python -m pip install -e ".[dev,diagnostics]" -e ./packages/osp-sim`
and run `python -m pytest -ra`. See [testing](docs/developer-guide/testing.md)
and [contributing](CONTRIBUTING.md).

## License and citation

OSP uses [BSD-3-Clause](LICENSE). Cite Open Horizon Observatory,
*OHOBS Science Pipeline*, version 0.1.0rc2, using [CITATION.cff](CITATION.cff).
No DOI or PyPI publication is asserted. See [security reporting](SECURITY.md)
and the [code of conduct](CODE_OF_CONDUCT.md).
