"""Verify Core alone, or Core with Simulation, in a new isolated environment."""

import argparse
import os
import subprocess
import venv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("--wheelhouse", type=Path, help="optional offline dependency source")
    parser.add_argument("--sim-wheel", type=Path, help="also test the optional Simulation wheel")
    args = parser.parse_args()
    if args.work.exists():
        raise FileExistsError(args.work)
    args.work.mkdir(parents=True)
    environment = args.work / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
    executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    packages = [str(args.wheel.resolve())]
    if args.sim_wheel:
        packages = [packages[0] + "[diagnostics]", str(args.sim_wheel.resolve())]
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env["PYTHONNOUSERSITE"] = "1"
    extra = ["--no-index", "--find-links", str(args.wheelhouse)] if args.wheelhouse else []
    subprocess.run(
        [str(executable), "-m", "pip", "install", *extra, *packages],
        env=env,
        check=True,
    )
    subprocess.run([str(executable), "-m", "pip", "check"], env=env, check=True)
    scripts = Path(__file__).resolve().parent
    subprocess.run(
        [
            str(executable),
            str(scripts / "smoke_core.py"),
            str(args.work.resolve() / "fixture"),
            *(["--with-simulation"] if args.sim_wheel else []),
        ],
        env=env,
        check=True,
    )
    if args.sim_wheel:
        subprocess.run(
            [str(executable), str(scripts / "smoke_api.py"), str(args.work.resolve() / "api-data")],
            env=env,
            check=True,
        )


if __name__ == "__main__":
    main()
