# Development setup

Create an isolated environment using the [Windows](../installation/WINDOWS.md)
or [Linux](../installation/linux.md) guide. From the repository root:

```sh
python -m pip install -e ".[dev,diagnostics]" -e ./packages/osp-sim
python -m pip check
python -m pytest -ra
```

Core-only development omits the simulator and diagnostics extra. The simulator
must never become a production requirement. See [testing](testing.md) and
[source builds](../installation/from-source.md). Keep credentials in the process
environment and observations outside tracked source. Use generic relative paths
in examples and retain scientific validation records when changing behaviour.
