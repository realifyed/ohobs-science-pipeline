"""Independent-exposure estimators and their sampling uncertainty."""

import warnings

import numpy as np
from astropy.stats import sigma_clip

from .config import Calibration


def _estimate(stack, settings: Calibration):
    if settings.method == "median":
        return np.nanmedian(stack, axis=0), np.sum(np.isfinite(stack), axis=0)
    if settings.method == "clipped_mean":
        stack = sigma_clip(
            stack,
            sigma=settings.clip_sigma,
            maxiters=1,
            axis=0,
            cenfunc="median",
            stdfunc="mad_std",
            masked=False,
        )
    return np.nanmean(stack, axis=0), np.sum(np.isfinite(stack), axis=0)


def combine(stack, settings: Calibration):
    """Return estimate, estimator variance, temporal variance, and support counts.

    Robust methods resample entire input frames and rerun the estimator. The
    fixed RNG stream is identical for every tile and every pixel.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning, module=r"(numpy|scipy)(\.|$)")
        warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)
        warnings.filterwarnings(
            "ignore", message="All-NaN slice encountered", category=RuntimeWarning
        )
        warnings.filterwarnings("ignore", message="Degrees of freedom", category=RuntimeWarning)
        warnings.filterwarnings(
            "ignore", message="Input data contains invalid values", module=r"astropy(\.|$)"
        )
        result, count = _estimate(stack, settings)
        available = np.sum(np.isfinite(stack), axis=0)
        temporal = np.nanvar(stack, axis=0, ddof=1)
        if settings.method == "mean":
            variance = temporal / np.maximum(count, 1)
        else:
            rng = np.random.default_rng(0)
            total = np.zeros_like(result)
            squares = np.zeros_like(result)
            samples = np.zeros_like(count)
            for _ in range(settings.bootstrap_samples):
                sample, _ = _estimate(stack[rng.integers(len(stack), size=len(stack))], settings)
                valid = np.isfinite(sample)
                delta = np.where(valid, sample - total, 0)
                samples += valid
                total += delta / np.maximum(samples, 1)
                squares += delta * np.where(valid, sample - total, 0)
            variance = np.where(
                samples == settings.bootstrap_samples,
                squares / (settings.bootstrap_samples - 1),
                np.nan,
            )
    invalid = (count < settings.min_frames) | ~np.isfinite(variance)
    return (
        np.where(invalid, np.nan, result),
        np.where(invalid, np.nan, variance),
        np.where(invalid, np.nan, temporal),
        count,
        available - count,
    )
