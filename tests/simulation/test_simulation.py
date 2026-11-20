"""Test the installed simulation workflow against independent injected truth."""

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS

from ohobs_pipeline.config import load_config
from ohobs_pipeline.dq import DQ, flag_cosmic_candidates
from ohobs_pipeline.ingest import FitsError, inspect_frame
from ohobs_pipeline.integrity import digest
from ohobs_pipeline.masters import CalibrationError, build_master, compatible
from ohobs_pipeline.pipeline import reduce_exposure
from ohobs_pipeline.products import read_calibrated
from ohobs_pipeline.reporting import exposure_report, write_html_report

pytest.importorskip("ohobs_sim")
from ohobs_sim.generator import GENERATOR_ORIGIN, Simulation, generate_dataset

pytestmark = [pytest.mark.simulation, pytest.mark.scientific]


def _masters(root, config):
    dark = build_master(list((root / "dark").glob("*.fits")), config)
    short = build_master(list((root / "flat_dark").glob("*.fits")), config)
    flat = build_master(list((root / "flat").glob("*.fits")), config, flat_dark_id=short.id)
    return dark, flat


def test_simulation_reproducible_and_physically_reduced(tmp_path):
    settings = Simulation(lights=2, masters=8)
    root = tmp_path / "synthetic"
    first = generate_dataset(root, settings, adversarial=True)
    second = generate_dataset(tmp_path / "repeat", settings, adversarial=True)
    assert first == second
    assert first["generator"] == dict(zip(("id", "version"), GENERATOR_ORIGIN, strict=True))
    assert all(digest(root / path) == checksum for path, checksum in first["checksums"].items())
    config = load_config(root / "simulation.yaml")
    dark, flat = _masters(root, config)
    light = root / "light/light-00000.fits"
    before = digest(light)
    assert inspect_frame(light, config).origin == GENERATOR_ORIGIN
    product = Path(reduce_exposure(light, config, dark_id=dark.id, flat_id=flat.id)["path"])
    result = read_calibrated(product)
    truth, header = fits.getdata(root / "truth.fits", header=True)
    response = fits.getdata(root / "truth.fits", "RESPONSE")
    truth = truth * np.median(response) / settings.gain
    normalized = (result.science - truth) / np.sqrt(result.variance)
    assert abs(np.nanmedian(normalized)) < 0.12
    assert 0.88 < np.nanstd(normalized) < 1.16
    report = exposure_report(product)
    assert digest(light) == before
    assert report["integrity"] == "VERIFIED"
    assert report["quality"]["source_count"] >= 10
    cat = Table.read(root / "truth.ecsv")
    wcs = WCS(header)
    np.testing.assert_allclose(
        wcs.pixel_to_world_values(cat["x"], cat["y"]), [cat["ra"], cat["dec"]], atol=1e-12
    )
    expected = np.column_stack((cat["x"], cat["y"]))
    measured = np.asarray([(s["x"], s["y"]) for s in report["quality"]["sources"]])
    distance = np.min(np.linalg.norm(measured[:, None] - expected[None], axis=2), axis=1)
    assert np.median(distance) < 0.3
    write_html_report(tmp_path / "report.html", report)
    assert "OHOBS OSP exposure report" in (tmp_path / "report.html").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        generate_dataset(root, settings)
    with pytest.raises(FitsError):
        inspect_frame(root / "faults/truncated.fits", config)
    assert not compatible(
        dark, inspect_frame(root / "faults/wrong-temperature-dark.fits", config), config, "DARK"
    )
    raw_like = tmp_path / "raw-like.fits"
    with fits.open(light) as hdus:
        del hdus[0].header["SIMULATE"]
        hdus.writeto(raw_like, checksum=True)
    with pytest.raises(FitsError, match="synthetic FITS identity"):
        inspect_frame(raw_like, config)


def test_defect_and_zero_scenarios(tmp_path):
    root = tmp_path / "defects"
    generate_dataset(root, Simulation(profile="defects", masters=5, lights=1), adversarial=True)
    config = load_config(root / "simulation.yaml")
    dark, flat = _masters(root, config)
    light = root / "light/light-00000.fits"
    product = Path(
        reduce_exposure(light, config, mode="calibrate", dark_id=dark.id, flat_id=flat.id)["path"]
    )
    data = read_calibrated(product)
    assert data.dq[7, 8] & int(DQ.DEAD_PIXEL)
    assert data.dq[8, 7] & int(DQ.HOT_PIXEL)
    assert np.count_nonzero(data.dq & int(DQ.SATURATED)) > 0
    with pytest.raises(CalibrationError):
        build_master(
            [*list((root / "flat").glob("*.fits"))[:4], root / "faults/saturated-flat.fits"], config
        )
    empty = tmp_path / "zero"
    manifest = generate_dataset(empty, Simulation(profile="zero", masters=5, lights=1))
    assert manifest["source_count"] == 0
    assert not np.any(fits.getdata(empty / "truth.fits"))


def test_bias_only_uses_disjoint_zero_exposure_masters(tmp_path):
    root = tmp_path / "bias"
    generate_dataset(root, Simulation(dark_e_s=0, masters=20, lights=1))
    config = load_config(root / "simulation.yaml")
    config = config.model_copy(
        update={
            "calibration": config.calibration.model_validate(
                {
                    "bias_only_max_exposure_s": 120,
                    "bias_only_evidence": "injected zero dark current",
                }
            )
        }
    )
    biases = sorted((root / "bias").glob("*.fits"))
    science_bias = build_master(biases[:10], config)
    flat_bias = build_master(biases[10:], config)
    flat = build_master(list((root / "flat").glob("*.fits")), config, flat_dark_id=flat_bias.id)
    light = root / "light/light-00000.fits"
    receipt = reduce_exposure(
        light, config, mode="calibrate", dark_id=science_bias.id, flat_id=flat.id
    )
    assert fits.getheader(receipt["path"])["BIASONLY"]
    assert read_calibrated(Path(receipt["path"])).noise_status == "CONDITIONAL"
    with pytest.raises(CalibrationError, match="share frames"):
        reduce_exposure(light, config, mode="calibrate", dark_id=flat_bias.id, flat_id=flat.id)


def test_cosmic_screen_preserves_science_and_rejects_well_sampled_psf():
    y, x = np.indices((64, 64))
    image = 40 + 600 * np.exp(-((x - 36) ** 2 + (y - 36) ** 2) / (2 * 1.75**2))
    image[11, 13] += 1000
    before = image.copy()
    dq = np.zeros(image.shape, dtype=np.uint16)
    assert flag_cosmic_candidates(image, np.full(image.shape, 16.0), dq, 10) == 1
    assert dq[11, 13] == int(DQ.COSMIC_RAY_CANDIDATE)
    assert dq[36, 36] == 0
    np.testing.assert_array_equal(image, before)
