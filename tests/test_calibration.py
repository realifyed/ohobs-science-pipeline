import numpy as np
import pytest
from astropy.io import fits
from conftest import frame_file

from ohobs_pipeline.combination import combine
from ohobs_pipeline.config import Calibration
from ohobs_pipeline.dq import DQ
from ohobs_pipeline.ingest import FitsError, inspect_frame
from ohobs_pipeline.integrity import digest
from ohobs_pipeline.masters import CalibrationError, select_master
from ohobs_pipeline.pipeline import reduce_exposure
from ohobs_pipeline.products import read_calibrated, validate_product
from ohobs_pipeline.reduction import apply_calibration, propagate


def test_end_to_end(dataset):
    light, config = dataset["light"], dataset["config"]
    original = digest(light)
    report = reduce_exposure(light, config)
    from pathlib import Path

    product = Path(report["path"])
    assert report["state"] == "PARTIAL"
    assert report["wcs"] == "FAILED"
    assert report["noise"] == "CONDITIONAL"
    image = read_calibrated(product)
    reference = dataset["truth"]
    valid = image.dq == 0
    valid[3, 1] = False  # Deliberate negative override, outside the simulated ensemble.
    standard = (image.science - reference)[valid] / np.sqrt(image.variance[valid])
    assert abs(np.median(standard)) < 0.06
    assert 0.94 < np.std(standard) < 1.07
    assert np.isnan(image.science[3, 3])
    assert image.dq[3, 3] & DQ.FLAT_INVALID
    assert image.dq[1, 0] & DQ.NONFINITE
    assert image.dq[2, 1] & (DQ.SATURATED | DQ.NONLINEAR_RESPONSE) == 0x402
    assert image.dq[2, 2] & DQ.BAD_PIXEL
    assert image.dq[2, 3] == DQ.NONLINEAR_RESPONSE
    assert image.science[3, 1] < 0
    assert digest(light) == original
    assert reduce_exposure(light, config)["reused"]
    from ohobs_pipeline.integrity import read_json

    qc = read_json(product.parent / "qc.json")
    assert qc["status"] == "PASS"
    assert qc["source_count"] == 3
    assert abs(qc["fwhm_px"] - 3.60) < 0.12
    assert abs(qc["ellipticity"] - (1 - 1.3 / 1.8)) < 0.05
    assert (
        abs(qc["sources"][0]["flux"] - 2 * np.pi * 700 * 1.8 * 1.3) / (2 * np.pi * 700 * 1.8 * 1.3)
        < 0.08
    )
    assert any(abs(s["x"] - 19.2) < 0.15 and abs(s["y"] - 19.85) < 0.15 for s in qc["sources"])
    (product.parent / "qc.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        validate_product(product)


@pytest.mark.parametrize(
    "edits",
    [
        {"EXPTIME": 121},
        {"CCD-TEMP": -9.9},
        {"GAIN": 31},
        {"READOUTM": "other"},
        {"XORGSUBF": 1},
        {"OFFSET": 31},
        {"CAMERAID": "different"},
        {"XBINNING": 2},
        {"BUNIT": "electron"},
    ],
)
def test_dark_mismatch(tmp_path, dataset, edits):
    path = tmp_path / "incompatible.fit"
    frame_file(path, dataset["raw"], "LIGHT", 120)
    with fits.open(path, mode="update") as hdus:
        hdus[0].header.update(edits)
    config = dataset["config"]
    with pytest.raises(CalibrationError, match="found 0"):
        select_master(inspect_frame(path, config), config, "DARK")
    with pytest.raises(CalibrationError, match="found 0"):
        select_master(
            inspect_frame(
                frame_file(tmp_path / "other.fit", dataset["raw"], "LIGHT", 120, filter_name="o"),
                config,
            ),
            config,
            "FLAT",
        )


def test_unavailable_gain(dataset):
    config = dataset["config"].model_copy(
        update={"detector": dataset["config"].detector.model_copy(update={"gain_e_per_adu": None})}
    )
    image = apply_calibration(
        inspect_frame(dataset["light"], config), dataset["dark"], dataset["flat"], config
    )
    assert image.noise_status == "UNAVAILABLE"
    assert np.isnan(image.variance).all()
    assert np.isfinite(image.science).any()


def test_unsigned_blank_and_truncation(tmp_path):
    path = tmp_path / "with spaces.fits"
    hdu = fits.PrimaryHDU(np.array([[-32768, -1, 7, 32767]], dtype=np.int16))
    hdu.header["BZERO"] = 32768
    hdu.header["BLANK"] = -1
    hdu.writeto(path)
    frame = inspect_frame(path)
    with frame.image() as im:
        np.testing.assert_equal(im.rows(0, 1), [[0, np.nan, 32775, 65535]])
    with path.open("rb+") as stream:
        stream.truncate(2880)
    with pytest.raises(FitsError, match="truncated"):
        inspect_frame(path)


def test_mean_and_robust_estimators():
    values = np.arange(16.0, dtype=float)
    values[-1] = 1000.0
    values = values[:, None, None]
    mean, variance, temporal, _, _ = combine(values, Calibration())
    assert mean.item() == values.mean()
    np.testing.assert_allclose(variance, temporal / 16)
    for method in ("median", "clipped_mean"):
        model = Calibration(method=method, min_frames=12)
        mean, variance, _, count, rejected = combine(values, model)
        assert mean.item() < 10
        assert variance.item() > 0
        assert count.item() + rejected.item() == 16
        np.testing.assert_equal(variance, combine(values, model)[1])


def test_monte_carlo_variance():
    rng = np.random.default_rng(4308)
    n, gain, offset, dark_e, read_e, true_f = 70000, 2.0, 600.0, 16.0, 4.0, 0.8
    master_n = 24
    fd_variance = 0.00003
    for photo_e in (0.0, 200.0, 4000.0):
        dark = (
            offset
            + (rng.poisson(dark_e, (master_n, n)) + rng.normal(0, read_e, (master_n, n))) / gain
        )
        raw = offset + (rng.poisson(photo_e + dark_e, n) + rng.normal(0, read_e, n)) / gain
        flat = rng.normal(true_f, np.sqrt(fd_variance), n)
        temporal = np.var(dark, axis=0, ddof=1)
        out = propagate(
            raw,
            dark.mean(axis=0),
            flat,
            temporal / master_n,
            np.full(n, fd_variance),
            temporal,
            gain,
            np.zeros(n, "uint16"),
            0.1,
        )
        # Standard error for variance at n=70k is ~0.54%; tolerance also
        # covers finite flat linearization and the constrained photo estimator.
        measured = np.var(out.science)
        prediction = np.mean(out.variance)
        if photo_e:
            assert abs(measured / prediction - 1) < 0.025
        else:
            assert (out.science < 0).any()
            assert 0.85 < measured / prediction < 1


def test_astropy_independent_arithmetic():
    from astropy.nddata import CCDData, VarianceUncertainty

    raw = np.array([200.0, 199.0, 275.0])
    dark = np.array([201.0, 199.0, 205.0])
    flat = np.array([0.7, 1.0, 1.15])
    dark_var = np.array([0.1, 0.2, 0.3])
    flat_var = np.array([0.002, 0.004, 0.005])
    temporal = np.array([3.0, 4.0, 5.0])
    gain = 2.0
    independent = (
        CCDData(
            raw,
            unit="adu",
            uncertainty=VarianceUncertainty(temporal + np.maximum(raw - dark, 0) / gain),
        )
        .subtract(CCDData(dark, unit="adu", uncertainty=VarianceUncertainty(dark_var)))
        .divide(CCDData(flat, unit="", uncertainty=VarianceUncertainty(flat_var)))
    )
    ours = propagate(
        raw, dark, flat, dark_var, flat_var, temporal, gain, np.zeros(3, dtype=np.uint16), 0.1
    )
    np.testing.assert_allclose(ours.science, independent.data)
    np.testing.assert_allclose(ours.variance, independent.uncertainty.array)


def test_smoothed_detection_fits_original_pixels():
    from ohobs_pipeline.config import Quality
    from ohobs_pipeline.quality import measure
    from ohobs_pipeline.reduction import Calibrated

    y, x = np.indices((64, 64))
    rng = np.random.default_rng(123)
    science = rng.normal(50, 2, x.shape)
    science += 500 * np.exp(-0.5 * (((x - 30.3) / 2.1) ** 2 + ((y - 31.2) / 2.8) ** 2))
    image = Calibrated(science, np.full(x.shape, 4.0), np.zeros(x.shape, np.uint16), "CONDITIONAL")
    _, sources = measure(image, Quality(fit_radius=10, detection_smoothing_sigma_px=2))
    assert len(sources) == 1
    source = sources[0]
    np.testing.assert_allclose([source.x, source.y], [30.3, 31.2], atol=0.05)
    np.testing.assert_allclose(source.fwhm, 2.35482 * np.sqrt(2.1 * 2.8), atol=0.1)
