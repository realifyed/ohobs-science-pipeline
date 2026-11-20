"""Checks for scientifically plausible output that a structural test can miss."""

from pathlib import Path

import numpy as np
import pytest
from astropy import units as u
from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
from astropy.wcs import WCS
from conftest import frame_file

from ohobs_pipeline.astrometry import _catalogue
from ohobs_pipeline.config import Calibration
from ohobs_pipeline.dq import DQ
from ohobs_pipeline.integrity import read_json
from ohobs_pipeline.masters import CalibrationError, build_master, verify_flat_lineage
from ohobs_pipeline.pipeline import reduce_exposure
from ohobs_pipeline.products import validate_product
from ohobs_pipeline.reduction import propagate


def test_flat_lineage_respects_consumer_policy(dataset, tmp_path):
    config = dataset["config"]
    loose = config.model_copy(
        update={
            "calibration": Calibration(
                temperature_tolerance_c=0.25, temperature_evidence="synthetic by construction"
            )
        }
    )
    rng = np.random.default_rng(882)
    short = [
        frame_file(
            tmp_path / f"loose-{i}.fit",
            rng.normal(1000, 2, dataset["raw"].shape),
            "FLAT_DARK",
            4,
            temp=-9.8,
        )
        for i in range(6)
    ]
    dep = build_master(short, loose)
    paths = [Path(f["path"]) for f in dataset["flat"].manifest["frames"]]
    flat = build_master(paths, loose, flat_dark_id=dep.id)
    assert verify_flat_lineage(flat, loose).id == dep.id
    with pytest.raises(CalibrationError, match="current matching policy"):
        verify_flat_lineage(flat, config)
    with pytest.raises(CalibrationError, match="current matching policy"):
        reduce_exposure(dataset["light"], config, flat_id=flat.id, dry_run=True)


def test_degenerate_flat_is_rejected(dataset, tmp_path):
    config = dataset["config"]
    paths = [Path(f["path"]) for f in dataset["flat"].manifest["frames"]]
    path = frame_file(tmp_path / "uniform.fit", np.full(dataset["raw"].shape, 16000.0), "FLAT", 4)
    with pytest.raises(CalibrationError, match="constant or wholly masked"):
        build_master(paths[:5] + [path], config, flat_dark_id=dataset["flat_dark"].id)


def test_flat_peak_code_screen_rejects_nearly_constant_input(dataset, tmp_path):
    config = dataset["config"]
    config = config.model_copy(
        update={
            "calibration": config.calibration.model_copy(
                update={"flat_peak_code_fraction_max": 0.99}
            )
        }
    )
    paths = [Path(f["path"]) for f in dataset["flat"].manifest["frames"]]
    values = np.full(dataset["raw"].shape, 16000.0)
    values[-1, -1] = 15000.0
    path = frame_file(tmp_path / "peak.fit", values, "FLAT", 4)
    with pytest.raises(CalibrationError, match="peak-code occupancy"):
        build_master(paths[:5] + [path], config, flat_dark_id=dataset["flat_dark"].id)


def test_error_status_when_dark_is_quantized_or_invalid():
    raw = np.array([200.0, 205.0, 190.0, 220.0, np.nan])
    dark = np.full(5, 200.0)
    flat = np.array([1.0, 1.0, 1.0, 0.0, 1.0])
    err = np.array([0.01, 0.01, 0.01, 0.01, 0.01])
    temporal = np.array([0.0, 4.0, np.nan, 4.0, 4.0])
    flags = np.zeros(5, dtype=np.uint16)
    img = propagate(raw, dark, flat, err, err, temporal, 2.0, flags, 0.1)
    assert img.noise_status == "PARTIAL"
    assert np.isfinite(img.variance).tolist() == [False, True, False, False, False]
    assert img.science[2] == -10
    assert img.dq[3] & DQ.FLAT_INVALID
    assert img.dq[4] & DQ.NONFINITE
    with pytest.raises(ValueError, match="positive and finite"):
        propagate(raw, dark, flat, err, err, temporal, 0.0, flags, 0.1)


def test_fits_semantics_even_with_valid_checksums(dataset, tmp_path):
    cfg = dataset["config"]
    result = reduce_exposure(dataset["light"], cfg, mode="calibrate")
    path = Path(result["path"])
    no_gain = cfg.model_copy(
        update={"detector": cfg.detector.model_copy(update={"gain_e_per_adu": None})}
    )
    unavailable = reduce_exposure(dataset["light"], no_gain, mode="calibrate")
    with fits.open(unavailable["path"]) as hdus:
        assert hdus[0].header["ERRSTAT"] == "UNAVAILABLE"
        assert np.isnan(hdus["ERR"].data).all()
        assert np.isfinite(hdus["SCI"].data).any()
    with fits.open(path) as hdus:
        assert hdus["ERR"].header["BUNIT"] == hdus["SCI"].header["BUNIT"] == "adu"
        assert hdus[0].header["TIMESYS"] == "UTC"
        assert (
            hdus[0].header["OBS_ID"]
            == read_json(path.parent / "provenance.json")["definition"]["input_sha256"]
        )
        invalid = tmp_path / "lying-valid-checksums.fits"
        hdus[0].header["ERRSTAT"] = "UNAVAILABLE"
        hdus.writeto(invalid, checksum=True)
        with pytest.raises(ValueError, match="ERRSTAT"):
            validate_product(invalid, provenance=False)
        hdus[0].header["ERRSTAT"] = "CONDITIONAL"
        hdus["DQ"].data[25, 25] |= int(DQ.SATURATED)
        invalid = tmp_path / "invalid-sci-mask.fits"
        hdus.writeto(invalid, checksum=True)
        with pytest.raises(ValueError, match="pixel or uncertainty"):
            validate_product(invalid, provenance=False)
        hdus["DQ"].data[25, 25] = 0
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        wcs.wcs.crval = [10.0, 20.0]
        wcs.wcs.cdelt = [-0.001, 0.001]
        hdus["SCI"].header.update(wcs.to_header())
        invalid = tmp_path / "unverified-wcs.fits"
        hdus.writeto(invalid, checksum=True)
        with pytest.raises(ValueError, match="WCSSTAT"):
            validate_product(invalid, provenance=False)


def test_catalogue_tagged_units_and_incompatible_units(tmp_path):
    table = Table(
        {
            "ra": [np.pi],
            "dec": [0.25],
            "ref_epoch": [2016.0],
            "source_id": [123],
            "pmra": [0.0],
            "pmdec": [0.0],
        }
    )
    table["ra"].unit = table["dec"].unit = u.rad
    path = tmp_path / "catalogue.ecsv"
    table.write(path)
    result = _catalogue(path, Time(2016, format="jyear", scale="tcb"))
    np.testing.assert_allclose(result.ra.deg, [180.0])
    table["ra"].unit = u.m
    table.write(path, overwrite=True)
    with pytest.raises(u.UnitConversionError):
        _catalogue(path, Time(2016, format="jyear", scale="tcb"))


def test_independent_master_planes_and_shared_flat_dark_variance(dataset):
    for role in ("dark", "flat", "flat_dark"):
        master = dataset[role]
        raws = np.array([fits.getdata(f["path"]) for f in master.manifest["frames"]])
        with master.images() as planes:
            first, last = 10, 25
            actual = planes["DATA"].rows(first, last)
            actual_var = planes["VAR"].rows(first, last)
            m = raws[:, first:last].mean(axis=0)
            v = raws[:, first:last].var(axis=0, ddof=1) / len(raws)
        if role == "flat":
            dep = dataset["flat_dark"]
            raws2 = np.array([fits.getdata(f["path"]) for f in dep.manifest["frames"]])
            m -= raws2[:, first:last].mean(axis=0)
            v += raws2[:, first:last].var(axis=0, ddof=1) / len(raws2)
            norm = master.manifest["normalization"]
            m, v = m / norm, v / norm**2
        valid = np.isfinite(actual)
        np.testing.assert_allclose(actual[valid], m[valid], rtol=2e-13, atol=2e-12)
        np.testing.assert_allclose(actual_var[valid], v[valid], rtol=2e-12, atol=1e-14)


def test_high_signal_coverage_and_aperture_uncertainty():
    rng = np.random.default_rng(203581)
    n = 85000
    g = 2.0
    de = 24.0
    signal = 2400.0
    flat = 0.85
    # Independent exposures, Poisson photoelectrons and independent Gaussian read noise.
    sampled_darks = 650 + (rng.poisson(de, (24, n)) + rng.normal(0, 4, (24, n))) / g
    light = 650 + (rng.poisson(de + signal * flat, n) + rng.normal(0, 4, n)) / g
    flats = flat + rng.normal(0, 0.001, n)
    temporal = sampled_darks.var(axis=0, ddof=1)
    out = propagate(
        light,
        sampled_darks.mean(axis=0),
        flats,
        temporal / 24,
        np.full(n, 1.0e-6),
        temporal,
        g,
        np.zeros(n, "uint16"),
        0.1,
    )
    z = (out.science - signal / g) / np.sqrt(out.variance)
    # Five binomial standard errors at n=85k, rounded up for first-order terms.
    assert abs(np.mean(np.abs(z) <= 1) - 0.6826895) < 0.009
    assert abs(np.mean(np.abs(z) <= 1.96) - 0.9500042) < 0.004
    assert abs(z.mean()) < 0.028
    assert 0.980 < np.std(z, ddof=1) < 1.020
    science = out.science.reshape(-1, 25).sum(axis=1)
    apvar = out.variance.reshape(-1, 25).sum(axis=1)
    # Approximate sampling SE sqrt(2/(3400-1)) of the variance ratio is 2.43%.
    assert 0.88 < np.var(science, ddof=1) / apvar.mean() < 1.12
    print(
        f"bright MC mean={z.mean():.6f} sd={np.std(z, ddof=1):.6f} "
        f"coverage={np.mean(abs(z) <= 1):.6f},{np.mean(abs(z) <= 1.96):.6f} "
        f"aperture_ratio={np.var(science, ddof=1) / apvar.mean():.6f}"
    )
