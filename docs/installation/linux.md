# Linux installation (Bash)

Linux is a CI target; no Linux runtime was available for this local audit.
These commands follow the actual root packaging layout. Full installation,
tests and external solver operation still require Linux execution. macOS is
not advertised as verified.

Use Python >=3.11 (the metadata floor), its venv module, pip and Git.
Run from the repository root:

```bash
git clone https://github.com/realifyed/ohobs-science-pipeline.git
cd ohobs-science-pipeline
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
osp --help
osp doctor
python -m pip check
python scripts/smoke_core.py scratch/linux-demo
```

Dependencies resolve from metadata. Use a Python/architecture combination
with NumPy, SciPy and Astropy wheels; compiling those dependencies requires
their upstream build prerequisites. Do not use sudo pip. If venv is missing,
install your distribution's Python venv component. Calibration and QC do not
need an external solver.

Install native Astrometry.net and suitable indexes following its
[upstream instructions](https://astrometry.net/doc/readme.html), then set
`astrometry.backend: astrometry_net` and `executable: solve-field`.
`backend_config` can point to its index configuration. Probe with
`osp astrometry probe --config observatory.yaml`. A help probe proves launch,
not indexed solving or independent verification.

`local` and `auto` refer to ANSVR-compatible HTTP, not native solve-field.
The Windows ANSVR installer is not a Linux installation method. Native Linux
integration is implemented but untested here with actual indexes. See
[astrometry](../user-guide/astrometry.md), [source installation](from-source.md)
and [troubleshooting](troubleshooting.md).
