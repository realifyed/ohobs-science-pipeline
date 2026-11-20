"""Independent discrete-Poisson/continuous-Gaussian calculation for the zero case."""

import json

import numpy as np
from scipy.special import ndtr
from scipy.stats import norm, poisson


def analyze() -> dict:
    """Calculate coverage without treating standardized residuals as normal."""
    m = 32
    dark = 3.0
    read_var = 16.0
    draws = 180000
    k = np.arange(36)[:, None]
    summed_master = np.arange(212)[None, :]
    weights = poisson.pmf(k, dark) * poisson.pmf(summed_master, m * dark)
    assert 1 - weights.sum() < 1e-12
    mean = k - summed_master / m
    sigma = np.sqrt(read_var * (1 + 1 / m))
    base = (dark + read_var) * (1 + 1 / m)
    positive_mean = np.sum(weights * (sigma * norm.pdf(mean / sigma) + mean * ndtr(mean / sigma)))
    intervals = []
    for width in (1, 1.96):
        low = -width * np.sqrt(base)
        high = (width**2 + np.sqrt(width**4 + 4 * width**2 * base)) / 2
        clip_coverage = np.sum(weights * (ndtr((high - mean) / sigma) - ndtr((low - mean) / sigma)))
        fixed = width * np.sqrt(base)
        independent_coverage = np.sum(
            weights * (ndtr((fixed - mean) / sigma) - ndtr((-fixed - mean) / sigma))
        )
        intervals.append(
            {
                "width_err": width,
                "plugin_coverage": float(clip_coverage),
                "independent_expectation_coverage": float(independent_coverage),
                "plugin_expected_mc_se": float(
                    np.sqrt(clip_coverage * (1 - clip_coverage) / draws)
                ),
            }
        )
    return {
        "model": "independent enumerated Poisson counts plus combined Gaussian read noise",
        "probability_mass": float(weights.sum()),
        "base_variance_e2": float(base),
        "plugin_variance_bias_fraction": float(positive_mean / base),
        "expected_independent_variance_bias_fraction": 0,
        "coverage": intervals,
    }


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, allow_nan=False))
