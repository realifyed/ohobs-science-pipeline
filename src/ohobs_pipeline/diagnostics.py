"""Local readiness checks. Network probing is separately authorized."""

import os
import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from . import __version__
from .config import Config
from .online_astrometry import KEY_ENV


def readiness(config: Config | None = None) -> dict:
    """Return per-capability checks with safe, non-secret diagnostics."""
    try:
        installed = version("ohobs-science-pipeline")
        package = {
            "status": "PASS" if installed == __version__ else "WARN",
            "distribution_version": installed,
            "imported_version": __version__,
        }
    except PackageNotFoundError:
        package = {"status": "WARN", "reason": "Source import. Install the wheel for CLI use."}
    result: dict = {
        "package": package,
        "nova_credentials": {
            "status": "PASS" if bool(os.environ.get(KEY_ENV, "").strip()) else "NOT_CONFIGURED"
        },
    }
    if config is None:
        return result
    work = config.work_dir.resolve()
    parent = next((p for p in (work, *work.parents) if p.is_dir()), Path.cwd())
    result.update(
        storage={
            "status": "PASS" if os.access(parent, os.W_OK) else "WARN",
            "check": "permission estimate for nearest existing directory",
            "free_bytes": shutil.disk_usage(parent).free,
        },
        detector={
            "status": "PASS" if config.detector.evidence else "WARN",
            "model": config.detector.model,
            "gain_configured": config.detector.gain_e_per_adu is not None,
        },
        calibration_library={
            "status": "PASS"
            if any((work / "masters").glob("*/manifest.json"))
            else "NOT_CONFIGURED",
        },
        reference_catalogue={
            "status": "NOT_CONFIGURED"
            if config.astrometry.catalogue is None
            else "PASS"
            if config.astrometry.catalogue.is_file()
            else "FAIL",
        },
        ansvr={
            "status": "NOT_CONFIGURED"
            if config.astrometry.backend not in {"local", "auto", "ansvr_http", "ansvr"}
            else "WARN",
            "reason": "Run doctor --probe to test the selected solver.",
        },
    )
    return result
