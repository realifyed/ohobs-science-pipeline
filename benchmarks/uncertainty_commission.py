"""Measure low-count coverage and shared-calibration covariance on controlled inputs."""

import json

import numpy as np

from ohobs_pipeline.reduction import propagate


def low_counts() -> list[dict]:
    """Use an independent Poisson plus Gaussian generative model in electrons."""
    rng = np.random.default_rng(781203)
    n, dark_rate, read_variance, master_size = 180_000, 3.0, 16.0, 32
    temporal = dark_rate + read_variance
    master_var = temporal / master_size
    results = []
    for signal in (0.0, 1.0, 5.0, 25.0, 100.0):
        raw = rng.poisson(signal + dark_rate, n) + rng.normal(0, np.sqrt(read_variance), n)
        master = rng.poisson(master_size * dark_rate, n) / master_size + rng.normal(
            0, np.sqrt(read_variance / master_size), n
        )
        one = np.ones(n)
        result = propagate(
            raw,
            master,
            one,
            one * master_var,
            one * 0,
            one * temporal,
            1.0,
            np.zeros(n, dtype=np.uint16),
            0.1,
        )
        error = result.science - signal
        variance_truth = signal + temporal + master_var
        normalized = error / np.sqrt(result.variance)
        results.append(
            {
                "signal_e": signal,
                "trials": n,
                "analytic_variance_e2": variance_truth,
                "empirical_variance_over_analytic": float(error.var(ddof=1) / variance_truth),
                "mean_osp_variance_over_analytic": float(result.variance.mean() / variance_truth),
                "normalized_mean": float(normalized.mean()),
                "within_1err": float(np.mean(np.abs(normalized) <= 1)),
                "within_1_96err": float(np.mean(np.abs(normalized) <= 1.96)),
                "negative_fraction": float(np.mean(result.science < 0)),
            }
        )
    return results


def shared_calibrators() -> dict:
    """Compare independent realizations to the first-order shared-master prediction."""
    rng = np.random.default_rng(83712)
    n = 240_000
    dvar, fvar = 1.6, 0.0001
    photo_a, photo_b = 60, 90
    common_dark = rng.normal(0, np.sqrt(dvar), n)
    common_flat = 1 + rng.normal(0, np.sqrt(fvar), n)
    x = (rng.poisson(photo_a, n) - common_dark) / common_flat
    y = (rng.poisson(photo_b, n) - common_dark) / common_flat
    covariance = float(np.cov(x, y)[0, 1])
    expected = dvar + photo_a * photo_b * fvar
    # One of five separated flat levels remains the median in every draw.
    # At this noise, the median pixel is independent of the two corner pixels.
    flat_means = np.array([7500, 9000, 10000, 11000, 12500], dtype=float)
    draws = flat_means + rng.normal(0, 50, (n, len(flat_means)))
    norm = np.median(draws, axis=1)
    assert np.all(norm == draws[:, 2])
    normalized = draws[:, [0, 4]] / norm[:, None]
    renormalized_cov = float(np.cov(normalized.T)[0, 1])
    predicted_renormalized = float(flat_means[0] * flat_means[4] * 50**2 / flat_means[2] ** 4)
    return {
        "trials": n,
        "cross_exposure_covariance_e2": covariance,
        "first_order_cross_exposure_covariance_e2": expected,
        "cross_pixel_covariance_normalized_flat": renormalized_cov,
        "first_order_cross_pixel_covariance": predicted_renormalized,
        "cross_exposure_covariance_standard_error_e2": float(
            np.std((x - x.mean()) * (y - y.mean()), ddof=1) / np.sqrt(n)
        ),
        "cross_pixel_covariance_standard_error": float(
            np.std(np.prod(normalized - normalized.mean(axis=0), axis=1), ddof=1) / np.sqrt(n)
        ),
    }


if __name__ == "__main__":
    print(
        json.dumps(
            {"low_counts": low_counts(), "shared_calibrators": shared_calibrators()}, indent=2
        )
    )
