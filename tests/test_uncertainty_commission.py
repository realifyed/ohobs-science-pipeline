"""Independent statistical checks of the marginal ERR assumptions."""

import runpy
from pathlib import Path


def test_low_count_variance_and_shared_calibration_limits():
    checks = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "benchmarks" / "uncertainty_commission.py")
    )
    low = checks["low_counts"]()
    # Under a normal approximation the relative sample-variance standard error
    # is sqrt(2/(n-1)). A 0.02 bound allows nearly six such standard errors,
    # including the modest excess kurtosis from Poisson signal.
    for row in low:
        assert abs(row["empirical_variance_over_analytic"] - 1) < 0.02
    assert 1.07 < low[0]["mean_osp_variance_over_analytic"] < 1.12
    assert 0.48 < low[0]["negative_fraction"] < 0.52
    assert abs(low[-1]["mean_osp_variance_over_analytic"] - 1) < 0.01

    cov = checks["shared_calibrators"]()
    assert (
        abs(cov["cross_exposure_covariance_e2"] - cov["first_order_cross_exposure_covariance_e2"])
        < 5 * cov["cross_exposure_covariance_standard_error_e2"]
    )
    assert (
        abs(
            cov["cross_pixel_covariance_normalized_flat"]
            - cov["first_order_cross_pixel_covariance"]
        )
        < 5 * cov["cross_pixel_covariance_standard_error"]
    )
