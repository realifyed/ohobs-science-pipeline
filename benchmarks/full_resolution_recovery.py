"""Interrupt a real child process after a staged partial write, then resume."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from threading import Lock
from time import perf_counter
from unittest.mock import patch

from ohobs_sim.generator import Simulation, generate_dataset

from ohobs_pipeline.config import load_config
from ohobs_pipeline.integrity import digest
from ohobs_pipeline.jobs import create_job, job_info, run_job
from ohobs_pipeline.masters import build_master

CRASH = """
import os, sys
from ohobs_pipeline import pipeline
from ohobs_pipeline.cli import main
def crash(path, *args, **kwargs):
    path.write_bytes(b'injected incomplete FITS')
    os._exit(28)
pipeline.write_science = crash
raise SystemExit(main(sys.argv[1:]))
"""


def run(root: Path) -> dict:
    generate_dataset(
        root,
        Simulation.model_validate(
            {"height": 2180, "width": 3856, "masters": 5, "lights": 3, "profile": "zero"}
        ),
    )
    config_path = root / "simulation.yaml"
    obj = json.loads(config_path.read_bytes())
    obj.update(workers=2, memory_mib=4096)
    config_path.write_text(json.dumps(obj), encoding="utf-8")
    config = load_config(config_path)
    raw = root / "light"
    original = {p: digest(p) for p in raw.glob("*.fits")}
    build_master(sorted((root / "dark").glob("*.fits")), config)
    flat_dark = build_master(sorted((root / "flat_dark").glob("*.fits")), config)
    build_master(sorted((root / "flat").glob("*.fits")), config, flat_dark_id=flat_dark.id)
    call = subprocess.run
    pending = True
    lock = Lock()

    def inject(args, *positional, **kwargs):
        nonlocal pending
        with lock:
            crash = pending and args[1:4] == ["-m", "ohobs_pipeline", "reduce"]
            if crash:
                pending = False
        command = [sys.executable, "-c", CRASH, *args[3:]] if crash else args
        return call(command, *positional, **kwargs)

    start = perf_counter()
    with patch("ohobs_pipeline.jobs.subprocess.run", inject):
        first = create_job(raw, config_path)
    interrupted_time = perf_counter() - start
    assert first["counts"] == {"FAILED": 1, "PARTIAL": 2}
    assert [r["outcome"]["returncode"] for r in first["frames"] if r["state"] == "FAILED"] == [28]
    staging = sorted((config.work_dir / "products").glob(".osp-*/science.fits"))
    assert len(staging) == 1
    start = perf_counter()
    resumed = run_job(config.work_dir, first["id"], retry=True)
    resume_time = perf_counter() - start
    assert resumed["counts"] == {"PARTIAL": 3}
    assert run_job(config.work_dir, first["id"]) == resumed
    assert original == {p: digest(p) for p in raw.glob("*.fits")}
    audit = job_info(config.work_dir, first["id"], verify_products=True)["product_integrity"]
    assert audit == {"VERIFIED": 3, "FAILED": 0}
    return {
        "geometry_yx": [2180, 3856],
        "workers": 2,
        "configured_memory_mib": 4096,
        "first": first["counts"],
        "after_retry": resumed["counts"],
        "audit": audit,
        "elapsed_before_retry_s": interrupted_time,
        "elapsed_retry_s": resume_time,
        "raw_hashes_unchanged": True,
        "staged_partial_not_published": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(run(parser.parse_args().output), indent=2))
