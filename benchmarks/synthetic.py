"""Run a full-size or small synthetic timing exercise with no observatory inputs."""

import argparse
import ctypes
import json
import os
import platform
import tempfile
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter

import numpy as np
from astropy.io import fits

from ohobs_pipeline.config import Config
from ohobs_pipeline.integrity import read_json, versions
from ohobs_pipeline.masters import build_master
from ohobs_pipeline.pipeline import reduce_exposure


def peak_rss_mib() -> float:
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("page_faults", wintypes.DWORD),
                ("peak_working_set", ctypes.c_size_t),
                ("unused", ctypes.c_size_t * 7),
            ]

        process = ctypes.windll.kernel32.GetCurrentProcess
        process.restype = wintypes.HANDLE
        metrics = ctypes.windll.psapi.GetProcessMemoryInfo
        metrics.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        stats = Counters()
        stats.cb = ctypes.sizeof(stats)
        if not metrics(process(), ctypes.byref(stats), stats.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return float(stats.peak_working_set / 2**20)
    import resource

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (2**20 if platform.system() == "Darwin" else 1024)


@contextmanager
def timed(results: dict, name: str):
    start = perf_counter()
    yield
    results[name] = perf_counter() - start


def run(root: Path, height: int, width: int, frames: int) -> dict:
    """Build matching synthetic masters, reduce a light and confirm product reuse."""
    rng = np.random.default_rng(2026)
    settings = Config.model_validate(
        {
            "node": "SYNTHETIC",
            "work_dir": root / "work",
            "memory_mib": 1024,
            "quality": {"min_sources": 1},
            "astrometry": {"executable": "unavailable-benchmark-solver"},
        }
    )
    durations: dict[str, float] = {}

    def write(name: str, kind: str, exp: int, level):
        raw = np.clip(
            rng.normal(level, np.sqrt(np.maximum(level - 992, 1)), (height, width)), 0, 65535
        ).astype(np.uint16)
        hdu = fits.PrimaryHDU(raw)
        hdu.header.update(
            {
                "IMAGETYP": kind,
                "EXPTIME": exp,
                "INSTRUME": "sim",
                "CAMERAID": "sim-1",
                "READOUTM": "full",
                "GAIN": 1,
                "OFFSET": 1,
                "XBINNING": 1,
                "YBINNING": 1,
                "BUNIT": "electron",
                "FILTER": "Ha",
                "OPTICID": "sim",
                "CCD-TEMP": -10,
                "XORGSUBF": 0,
                "YORGSUBF": 0,
                "DATE-OBS": "2024-07-01T00:00:00",
            }
        )
        path = root / (name + ".fits")
        hdu.writeto(path)
        return path

    response = np.linspace(0.8, 1.2, width)[None, :]
    with timed(durations, "generate"):
        d = [write(f"dark-{i}", "DARK", 120, 1000) for i in range(frames)]
        fd = [write(f"fd-{i}", "FLAT_DARK", 4, 995) for i in range(frames)]
        f = [write(f"flat-{i}", "FLAT", 4, 995 + response * 20000) for i in range(frames)]
        light = write("light", "LIGHT", 120, 1000 + response * 200)
    with timed(durations, "dark_master"):
        build_master(d, settings)
    with timed(durations, "flat_dark_master"):
        flat_dark = build_master(fd, settings)
    with timed(durations, "flat_master"):
        build_master(f, settings, flat_dark_id=flat_dark.id)
    with timed(durations, "reduce"):
        product = reduce_exposure(light, settings)
    phases = read_json(Path(product["path"]).parent / "provenance.json")["stages"]
    with timed(durations, "resume_existing_product"):
        assert reduce_exposure(light, settings)["reused"]
    return {
        "shape_yx": [height, width],
        "master_input_count_each": frames,
        "durations_s": durations,
        "stages": phases,
        "peak_rss_mib": peak_rss_mib(),
        "system": platform.platform(),
        "cpu": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "dependencies": versions(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape", nargs=2, type=int, default=(256, 256), metavar=("Y", "X"))
    parser.add_argument("--frames", type=int, default=5)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="osp-benchmark-") as folder:
        print(json.dumps(run(Path(folder), *args.shape, args.frames), indent=2))
