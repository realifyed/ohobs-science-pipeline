# Windows installation (PowerShell)

Package metadata requires Python >=3.11; current local verification uses
CPython 3.14.7. Other versions in CI are verification targets. Install Python
and Git, then run:

```powershell
git clone https://github.com/realifyed/ohobs-science-pipeline.git
cd ohobs-science-pipeline
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\osp.exe --help
.\.venv\Scripts\osp.exe doctor
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/smoke_core.py scratch/windows-demo
```

Run from the repository root. Activation is optional; these commands avoid
PowerShell activation-policy issues. Use a new demo directory. The fixture
is synthetic and included in Core's source tree; it needs no simulator.
`doctor` describes optional capabilities: exit zero alone does not establish
detector commissioning or working astrometry.

For later commands using bare osp, invoke `.\.venv\Scripts\osp.exe` or activate
with `.\.venv\Scripts\Activate.ps1`. Do not weaken machine-wide execution
policy just to activate an environment.

Python dependencies install automatically. Optional plots require
`.[diagnostics]`. The [historical constraints](../../configs/constraints-windows-py314.txt)
record an earlier tested Windows dependency set, not universal requirements.
Pass `-c configs/constraints-windows-py314.txt` to pip for that replay.

Calibration and QC run offline after installation. External solvers and indexes
are separate installations. [ANSVR](../commissioning/ANSVR-WINDOWS.md) is
Windows-oriented; [online solving](../user-guide/astrometry.md) requires explicit
upload authorization. See [source and editable installation](from-source.md),
[troubleshooting](troubleshooting.md) and [first reduction](../getting-started/first-reduction.md).
