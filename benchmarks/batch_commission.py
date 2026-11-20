"""Sample process-tree resident memory during batch execution."""

import argparse
import json
import platform
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import perf_counter

import numpy as np
import psutil
import yaml
from astropy.io import fits

from ohobs_pipeline.config import load_config
from ohobs_pipeline.integrity import versions
from ohobs_pipeline.jobs import create_job, run_job
from ohobs_pipeline.masters import build_master
from ohobs_pipeline.origin import stamp_origin


def image(path, data, kind, exposure, index):
    h = fits.PrimaryHDU(data.astype(np.uint16))
    stamp_origin(h.header, ("osp-batch-benchmark", "1"))
    h.header.update(
        {
            "INSTRUME": "OSP Synthetic",
            "CAMERAID": "OSP-SIM-01",
            "READOUTM": "Full",
            "GAIN": 30,
            "OFFSET": 30,
            "XBINNING": 1,
            "YBINNING": 1,
            "XORGSUBF": 0,
            "YORGSUBF": 0,
            "BUNIT": "electron",
            "CCD-TEMP": 18.9,
            "IMAGETYP": kind,
            "FILTER": "Ha",
            "OPTICID": "sim",
            "EXPTIME": exposure,
            "DATE-OBS": "2026-01-01T00:00:00",
            "SIMINDEX": index,
        }
    )
    h.writeto(path)
    return path


def timed_job(raw, config_path):
    root, end, samples = psutil.Process(), Event(), []
    child_usage = {}
    cpu_start = root.cpu_times()

    def sample():
        while not end.is_set():
            own = root.memory_info().rss
            children = []
            for child in root.children(recursive=True):
                try:
                    children.append(child.memory_info().rss)
                    cpu = child.cpu_times()
                    disk = child.io_counters()
                    child_usage[(child.pid, child.create_time())] = (
                        cpu.user + cpu.system,
                        disk.read_bytes,
                        disk.write_bytes,
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            samples.append((own, sum(children), len(children)))
            end.wait(0.05)

    monitor = Thread(target=sample)
    monitor.start()
    start = perf_counter()
    try:
        result = create_job(raw, config_path)
    finally:
        end.set()
        monitor.join()
    elapsed = perf_counter() - start
    cpu_end = root.cpu_times()
    work = load_config(config_path).work_dir
    before = perf_counter()
    again = run_job(work, result["id"])
    assert again == result
    return {
        "elapsed_s": elapsed,
        "resume_s": perf_counter() - before,
        "counts": result["counts"],
        "peak_parent_mib": max(p for p, c, n in samples) / 2**20,
        "peak_children_mib": max(c for p, c, n in samples) / 2**20,
        "peak_sum_mib": max(p + c for p, c, n in samples) / 2**20,
        "max_child_processes": max(n for p, c, n in samples),
        "parent_final_mib": root.memory_info().rss / 2**20,
        "sampled_worker_cpu_s": sum(row[0] for row in child_usage.values()),
        "parent_cpu_s": (cpu_end.user - cpu_start.user) + (cpu_end.system - cpu_start.system),
        "sampled_worker_read_bytes": sum(row[1] for row in child_usage.values()),
        "sampled_worker_write_bytes": sum(row[2] for row in child_usage.values()),
        "product_bytes": sum(
            p.stat().st_size for p in (work / "products").rglob("*") if p.is_file()
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", nargs="+", default=["1:1", "10:1", "10:2", "10:4", "100:2", "200:2"]
    )
    parser.add_argument("--shape", type=int, nargs="+", default=[128], metavar="PIXELS")
    args = parser.parse_args()
    if len(args.shape) not in (1, 2) or min(args.shape) < 16:
        parser.error("provide one square dimension or height and width, each at least 16")
    height, width = args.shape if len(args.shape) == 2 else args.shape * 2
    print(
        json.dumps(
            {
                "python": sys.version,
                "os": platform.platform(),
                "cpu": platform.processor(),
                "logical_cpus": psutil.cpu_count(),
                "rss_interval_ms": 50,
                "versions": versions(),
                "shape_yx": [height, width],
            }
        ),
        flush=True,
    )
    for case in args.cases:
        count, workers = map(int, case.split(":"))
        with TemporaryDirectory(prefix="osp-batch-benchmark-") as folder:
            root = Path(folder)
            cfg_path = root / "case.yaml"
            cfg_path.write_text(
                yaml.safe_dump(
                    {
                        "node": "SYNTHETIC",
                        "synthetic_test": True,
                        "work_dir": "work",
                        "workers": workers,
                        "memory_mib": 4096,
                        "astrometry": {"executable": "osp-known-absent-solver"},
                    }
                )
            )
            cfg = load_config(cfg_path)
            rng = np.random.default_rng(8293)
            shape = (height, width)
            response = np.linspace(0.85, 1.15, width)[None, :]
            for role, exp, level in (
                ("DARK", 120, 1000),
                ("FLAT_DARK", 3.75875, 990),
                ("FLAT", 3.75875, 990 + 10000 * response),
            ):
                files = [
                    image(root / f"{role}-{i}.fits", rng.normal(level, 4, shape), role, exp, i)
                    for i in range(5)
                ]
                build_master(files, cfg)
            raw = root / "raw"
            raw.mkdir()
            for i in range(count):
                image(
                    raw / f"light-{i:05}.fits",
                    rng.normal(1000 + 200 * response, 10, shape),
                    "LIGHT",
                    120,
                    i,
                )
            outcome = timed_job(raw, cfg_path)
            assert outcome["counts"] == {"PARTIAL": count}
            print(
                json.dumps(
                    {
                        "count": count,
                        "workers": workers,
                        **outcome,
                        "throughput_per_s": count / outcome["elapsed_s"],
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
