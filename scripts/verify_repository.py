"""Run release checks and save a sanitized transcript without private paths."""

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--live-gaia", action="store_true", help="also query the public Gaia test field"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run = root / "scratch" / datetime.now(UTC).strftime("verification-%Y%m%dT%H%M%S")
    run.mkdir(parents=True, exist_ok=False)
    commands = [
        ["-m", "pip", "check"],
        [
            "-m",
            "pytest",
            "-ra",
            "--basetemp",
            str(run / "pytest"),
            "-o",
            f"cache_dir={run / 'pytest-cache'}",
        ],
        ["-m", "ruff", "check", "src", "packages/osp-sim/src", "tests", "benchmarks", "scripts"],
        [
            "-m",
            "ruff",
            "format",
            "--check",
            "src",
            "packages/osp-sim/src",
            "tests",
            "benchmarks",
            "scripts",
        ],
        ["-m", "mypy", "src", "packages/osp-sim/src"],
        ["scripts/check_docs.py"],
        ["scripts/smoke_public_api.py"],
        ["-m", "build", "--outdir", str(run / "dist")],
        ["-m", "build", "packages/osp-sim", "--outdir", str(run / "dist")],
    ]
    if args.live_gaia:
        commands.insert(7, ["scripts/test_gaia_live.py", str(run / "live-gaia")])
    records = []

    def sanitize(text):
        for value, replacement in ((str(root), "<repository>"), (str(Path.home()), "<home>")):
            pattern = r"[\\/]+".join(re.escape(part) for part in re.split(r"[\\/]", value))
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        # Build tools can also emit the Windows 8.3 spelling of a home path.
        return re.sub(
            r"""[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s"'<>]+""",
            "<home>",
            text,
            flags=re.IGNORECASE,
        )

    def execute(arguments):
        print("Running:", sanitize("python " + " ".join(arguments)), flush=True)
        result = subprocess.run(
            [sys.executable, *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        records.append(
            {
                "command": sanitize("python " + " ".join(arguments)),
                "exit_code": result.returncode,
                "stdout": sanitize(result.stdout),
                "stderr": sanitize(result.stderr),
            }
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"verification failed; see {args.output}")

    for command in commands:
        execute(command)
    wheels = sorted((run / "dist").glob("*.whl"))
    execute(["-m", "twine", "check", "--strict", *map(str, sorted((run / "dist").iterdir()))])
    core = next(p for p in wheels if p.name.startswith("ohobs_science_pipeline-"))
    sim = next(p for p in wheels if p.name.startswith("ohobs_science_sim-"))
    execute(["scripts/check_wheel.py", str(core), str(run / "core")])
    execute(["scripts/check_wheel.py", str(core), str(run / "combined"), "--sim-wheel", str(sim)])
    execute(["scripts/check_wheel.py", ".", str(run / "source")])
    print(f"Passed {len(records)} release checks; transcript: {args.output}")


if __name__ == "__main__":
    main()
