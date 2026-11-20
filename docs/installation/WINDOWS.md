# Install OSP on Windows

In PowerShell 7 with Python 3.11 or newer, install the built wheel using
`python -m pip install PATH_TO_WHEEL` and run `osp doctor`. Use
`osp doctor --config CONFIG --backend local --probe` to check ANSVR HTTP.
Use `--backend online` with a rotated credential to check Nova login.
The [online guide](ONLINE_ASTROMETRY.md) explains secure key entry and
submission authorization. The [ANSVR commissioning guide](../commissioning/ANSVR-HTTP-VALIDATION.md)
covers service startup and independent Gaia checks.
