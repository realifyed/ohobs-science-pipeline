"""Controlled paired measurements for detector evidence."""

from pathlib import Path

import numpy as np
from scipy.stats import linregress

from .config import Config
from .ingest import inspect_frame, require_calibration_metadata
from .masters import detector_key


def characterize(sequence: dict, config: Config) -> dict:
    """Measure a paired photon-transfer sequence with dark pairs at every level.

    The operator marks the fit interval in advance. Exposure time is a proxy for
    dose only when the illumination is stable. All pixel values are in ADU.
    """
    if len(sequence["levels"]) < 4:
        raise ValueError("characterization needs at least four illumination levels")
    points = []
    read_noise_adu2, settings = [], None
    records: list[dict] = []
    used: set[str] = set()
    for level in sequence["levels"]:
        selection = [inspect_frame(Path(p), config) for p in (*level["flat"], *level["dark"])]
        if len(level["flat"]) != 2 or len(level["dark"]) != 2:
            raise ValueError("each level requires two flats and two matching darks")
        hashes = {f.sha256 for f in selection}
        if len(hashes) != 4 or hashes & used:
            raise ValueError("characterization reused an exposure")
        used.update(hashes)
        records.extend(f.manifest() for f in selection)
        exposure = selection[0].values["exposure"]
        if [f.values["kind"] for f in selection[:2]] != ["FLAT"] * 2 or any(
            f.values["kind"] not in ("DARK", "FLAT_DARK") for f in selection[2:]
        ):
            raise ValueError("sequence requires illumination flats and darks")
        for f in selection:
            require_calibration_metadata(f, config)
            key = {"detector": detector_key(f, config), "temperature": f.values["temp"]}
            if settings is None:
                settings = key
            if key != settings or f.values["exposure"] != exposure or f.values["unit"] != "adu":
                raise ValueError("incompatible characterization pair")
        if np.prod(selection[0].shape) * 96 > config.memory_mib * 2**20:
            raise ValueError("characterization exceeds configured memory")
        arrays = []
        for f in selection:
            with f.image() as image:
                arrays.append(image.rows(0, f.shape[0]))
        a, b, c, d = arrays
        valid = np.isfinite(a) & np.isfinite(b) & np.isfinite(c) & np.isfinite(d)
        if valid.sum() < 100:
            raise ValueError("too few finite pixels")
        a, b, c, d = (v[valid] for v in arrays)
        dark_var = np.var(c - d, ddof=1) / 2
        signal = float(np.mean((a + b - c - d) / 2))
        signal_var = float(np.var(a - b, ddof=1) / 2 - dark_var)
        point = {
            "exposure_s": exposure,
            "signal_adu": signal,
            "photo_variance_adu2": signal_var,
            "dark_variance_adu2": float(dark_var),
            "dark_mean_adu": float(np.mean((c + d) / 2)),
            "flat_pair_difference_adu": float(np.mean(a - b)),
            "fit": bool(level["fit"]),
        }
        points.append(point)
    if len({p["exposure_s"] for p in points}) != len(points):
        raise ValueError("use distinct doses at constant illumination")
    selected = [p for p in points if p["fit"]]
    if len(selected) < 3 or any(p["signal_adu"] <= 0 for p in selected):
        raise ValueError("select at least three positive unsaturated fit levels")
    transfer = linregress(
        [p["signal_adu"] for p in selected], [p["photo_variance_adu2"] for p in selected]
    )
    response = linregress([p["exposure_s"] for p in selected], [p["signal_adu"] for p in selected])
    if not np.isfinite(transfer.slope) or transfer.slope <= 0 or response.slope <= 0:
        raise ValueError("nonpositive gain or response slope")
    gain = 1 / transfer.slope
    for p in points:
        predicted = response.intercept + response.slope * p["exposure_s"]
        p["linearity_fractional_residual"] = (
            (p["signal_adu"] - predicted) / predicted if predicted > 0 else None
        )
    zeros = [Path(p) for p in sequence.get("bias_pair", [])]
    if zeros:
        if len(zeros) != 2:
            raise ValueError("bias_pair requires two files")
        for path in zeros:
            frame = inspect_frame(path, config)
            require_calibration_metadata(frame, config)
            key = {"detector": detector_key(frame, config), "temperature": frame.values["temp"]}
            if frame.values["kind"] != "BIAS" or frame.values["exposure"] != 0 or settings != key:
                raise ValueError("read-noise evidence requires matching zero-exposure bias frames")
            if frame.sha256 in used:
                raise ValueError("read-noise exposures must be independent")
            used.add(frame.sha256)
            records.append(frame.manifest())
            with frame.image() as image:
                read_noise_adu2.append(image.rows(0, frame.shape[0]))
        read_var = float(np.nanvar(read_noise_adu2[0] - read_noise_adu2[1], ddof=1) / 2)
        read_noise = float(np.sqrt(read_var) * gain) if np.isfinite(read_var) else None
    else:
        read_noise = None
    return {
        "schema_version": 1,
        "gain_e_per_adu": float(gain),
        "gain_regression_standard_error": float(transfer.stderr * gain**2),
        "read_noise_e": read_noise,
        "points": points,
        "settings": settings,
        "frames": records,
        "saturation_adu": None,
        "limitations": [
            "Fit range selected by operator. Saturation requires separate evidence.",
            "Regression error excludes illumination instability and correlated pixels.",
            "Read noise unavailable without a matched zero-exposure bias pair.",
        ],
    }
