"""Matched-dark, flat-corrected science arrays and marginal uncertainty."""

from contextlib import ExitStack
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .config import Config
from .dq import DQ, FATAL, characterized, flag_cosmic_candidates, raw_mask
from .ingest import Frame, inspect_frame, require_calibration_metadata
from .masters import CalibrationError, Master, compatible, reference_kind, verify_flat_lineage


@dataclass(frozen=True)
class Calibrated:
    science: NDArray[np.float64]
    variance: NDArray[np.float64]
    dq: NDArray[np.uint16]
    noise_status: str


def uncertainty_status(science, variance, gain: float | None) -> str:
    """Summarize positive finite variance coverage over finite science pixels."""
    if gain is None:
        return "UNAVAILABLE"
    reported = np.isfinite(variance)
    if not reported.any():
        return "UNAVAILABLE"
    if np.any(np.isfinite(science) & ~reported):
        return "PARTIAL"
    return "CONDITIONAL"


def propagate(
    raw,
    dark,
    flat,
    dark_variance,
    flat_variance,
    temporal,
    gain: float | None,
    dq,
    flat_minimum: float,
    expected_signal=None,
) -> Calibrated:
    """Apply the independent first-order model, conditional on flat normalization.

    Temporal dark variance estimates one exposure's read plus dark shot noise.
    Positive difference is a plug-in estimate of photoelectrons (including sky).
    """
    if gain is not None and (not np.isfinite(gain) or gain <= 0):
        raise ValueError("gain must be positive and finite")
    bad_flat = ~np.isfinite(flat) | (flat < flat_minimum)
    dq[bad_flat] |= int(DQ.FLAT_INVALID)
    dq[~np.isfinite(raw)] |= int(DQ.NONFINITE)
    dq[~np.isfinite(dark)] |= int(DQ.CALIBRATION_SUSPECT)
    valid = (dq & FATAL) == 0
    science = np.full(raw.shape, np.nan)
    variance = np.full(raw.shape, np.nan)
    with np.errstate(over="ignore", invalid="ignore"):
        numerator = raw - dark
        np.divide(numerator, flat, out=science, where=valid)
        if gain is not None:
            errors_valid = (
                valid
                & np.isfinite(dark_variance)
                & (dark_variance >= 0)
                & np.isfinite(flat_variance)
                & (flat_variance >= 0)
                & np.isfinite(temporal)
                & (temporal > 0)
            )
            signal = np.maximum(numerator, 0) if expected_signal is None else expected_signal
            if expected_signal is not None:
                errors_valid &= np.isfinite(signal) & (signal >= 0)
            noise = signal / gain + temporal + dark_variance
            derivative = science if expected_signal is None else signal / np.where(valid, flat, 1)
            np.divide(
                noise + derivative**2 * flat_variance, flat**2, out=variance, where=errors_valid
            )
    dq[valid & ~np.isfinite(science)] |= int(DQ.CALIBRATION_SUSPECT)
    science[~np.isfinite(science)] = np.nan
    variance[~np.isfinite(variance) | (variance <= 0) | ~np.isfinite(science)] = np.nan
    return Calibrated(science, variance, dq, uncertainty_status(science, variance, gain))


def apply_calibration(
    frame: Frame,
    dark: Master,
    flat: Master,
    config: Config,
    *,
    expectation_sha256: str | None = None,
) -> Calibrated:
    """Apply only compatible, independent matched calibration samples."""
    require_calibration_metadata(frame, config)
    if not compatible(dark, frame, config, reference_kind(config)) or not compatible(
        flat, frame, config, "FLAT"
    ):
        raise CalibrationError("incompatible science masters")
    d_def = dark.manifest["definition"]
    f_def = flat.manifest["definition"]
    if frame.values["kind"] != "LIGHT":
        raise CalibrationError("science calibration requires a LIGHT")
    fd_def = verify_flat_lineage(flat, config).manifest["definition"]
    if set(d_def["inputs"]).intersection(fd_def["inputs"]):
        raise CalibrationError(
            "science reference and flat reference share frames; covariance unknown"
        )
    if any(frame.sha256 in definition["inputs"] for definition in (d_def, f_def, fd_def)):
        raise CalibrationError("science input reused in its own master")
    if np.prod(frame.shape) * 112 > config.memory_mib * 2**20:
        raise CalibrationError("calibration arrays exceed configured memory budget")
    gain = (
        1.0
        if frame.values["unit"] == "electron"
        else config.detector.gain_e_per_adu
        if characterized(frame, config)
        else None
    )
    science = np.empty(frame.shape, dtype=np.float64)
    variance = np.empty_like(science)
    dq = np.empty(frame.shape, dtype=np.uint16)
    with ExitStack() as stack:
        raw = stack.enter_context(frame.image())
        d = stack.enter_context(dark.images())
        f = stack.enter_context(flat.images())
        expected = None
        if config.photon_expectation is not None:
            model = inspect_frame(config.photon_expectation)
            if (
                (expectation_sha256 is not None and model.sha256 != expectation_sha256)
                or model.sha256 == frame.sha256
                or model.header.get("OBS_ID") != frame.sha256
                or model.header.get("OSSIGNAL") != "INDEPENDENT"
                or model.origin != frame.origin
                or model.shape != frame.shape
                or model.values["unit"] != frame.values["unit"]
            ):
                raise CalibrationError(
                    "photon expectation is not matched to this observation, unit, or identity"
                )
            expected = stack.enter_context(model.image())
        for row in range(0, frame.shape[0], 128):
            end = min(frame.shape[0], row + 128)
            data = raw.rows(row, end)
            flags = raw_mask(data, frame, config, row)
            flags |= d["DQ"].rows(row, end).astype(np.uint16)
            flags |= f["DQ"].rows(row, end).astype(np.uint16)
            tile = propagate(
                data,
                d["DATA"].rows(row, end),
                f["DATA"].rows(row, end),
                d["VAR"].rows(row, end),
                f["VAR"].rows(row, end),
                d["TEMPVAR"].rows(row, end),
                gain,
                flags,
                config.calibration.flat_min_response,
                expected_signal=expected.rows(row, end) if expected is not None else None,
            )
            science[row:end], variance[row:end], dq[row:end] = tile.science, tile.variance, tile.dq
    if config.quality.cosmic_candidate_sigma is not None:
        flag_cosmic_candidates(science, variance, dq, config.quality.cosmic_candidate_sigma)
    return Calibrated(science, variance, dq, uncertainty_status(science, variance, gain))
