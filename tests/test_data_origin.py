"""Direct origin-policy tests that need only Core."""

import numpy as np
import pytest
import yaml
from astropy.io import fits
from conftest import frame_file, settings

from ohobs_pipeline.config import Config
from ohobs_pipeline.ingest import inspect_frame
from ohobs_pipeline.jobs import create_job
from ohobs_pipeline.masters import CalibrationError, Master, build_master, master_origin
from ohobs_pipeline.origin import ORIGIN_LABEL, OriginError, classify_origin, stamp_origin
from ohobs_pipeline.pipeline import reduce_exposure
from ohobs_pipeline.products import validate_product

MARKERS = {"SIMULATE": True, "ORIGIN": ORIGIN_LABEL, "SIMGEN": "osp-test-fixture", "SIMVER": "1"}


def test_origin_keywords_and_multi_hdu_conflicts():
    assert classify_origin(fits.Header()) == "observational"
    assert (
        classify_origin(fits.Header({"SIMULATE": False, "ORIGIN": "Observatory"}))
        == "observational"
    )
    marked = fits.Header(MARKERS)
    assert classify_origin(marked, fits.Header()) == ("osp-test-fixture", "1")
    for partial in (
        {"SIMULATE": True},
        {"SIMULATE": "T"},
        {"ORIGIN": ORIGIN_LABEL},
        {"SIMVER": "1"},
        {"CAMERAID": "OSP-SIM-old"},
        {**MARKERS, "SIMULATE": False},
    ):
        with pytest.raises(OriginError):
            classify_origin(fits.Header(partial))
    marked.append(("SIMVER", "2"))
    with pytest.raises(OriginError, match="contradictory"):
        classify_origin(marked)
    with pytest.raises(OriginError):
        classify_origin(fits.Header(MARKERS), fits.Header({"SIMULATE": False}))


def test_legacy_master_origin_needs_original_headers(tmp_path):
    row = {
        "sha256": "fixture",
        "original_header": fits.Header({"INSTRUME": "T1"}).tostring(sep="\n"),
    }
    definition = {"detector": {}, "inputs": ["fixture"]}
    assert (
        master_origin(Master(tmp_path, {"definition": definition, "frames": [row]}))
        == "observational"
    )
    with pytest.raises(CalibrationError, match="master origin is unverified"):
        master_origin(Master(tmp_path, {"definition": definition}))
    with pytest.raises(CalibrationError, match="master origin is unverified"):
        master_origin(
            Master(tmp_path, {"definition": {**definition, "detector": {"synthetic": True}}})
        )


def test_calibration_and_batch_require_explicit_homogeneous_origin(dataset, tmp_path):
    config = dataset["config"]
    real = dataset["light"]
    with fits.open(real) as hdus:
        stamp_origin(hdus[0].header, ("osp-test-fixture", "1"))
        synthetic = real.parent / "marked.fits"
        hdus.writeto(synthetic, checksum=True)

    with pytest.raises(OriginError, match="synthetic_test"):
        reduce_exposure(synthetic, config)
    test_config = config.model_copy(update={"synthetic_test": True})
    with pytest.raises(OriginError, match="observational input"):
        reduce_exposure(real, test_config)
    with pytest.raises(CalibrationError, match="compatible DARK"):
        reduce_exposure(synthetic, test_config)

    options = settings(tmp_path)
    for test_mode in (False, True):
        path = tmp_path / f"config-{test_mode}.yaml"
        path.write_text(yaml.safe_dump({**options, "synthetic_test": test_mode}), encoding="utf-8")
        with pytest.raises(OriginError, match="mixed data origins"):
            create_job(real.parent, path)
    assert not (config.work_dir / "jobs.sqlite3").exists()


def test_master_isolation_and_published_origin(tmp_path):
    config = Config.model_validate({**settings(tmp_path), "synthetic_test": True})
    y, x = np.indices((32, 40))

    def frames(kind, exp, level):
        return [
            frame_file(
                tmp_path / kind / f"{i}.fits", (level + i + x).astype(float), kind, exp, **MARKERS
            )
            for i in range(5)
        ]

    darks = frames("DARK", 120, 50)
    short = build_master(frames("FLAT_DARK", 4, 20), config)
    flat = build_master(frames("FLAT", 4, 800 + 2 * y), config, flat_dark_id=short.id)
    dark = build_master(darks, config)
    with fits.open(dark.directory / "master.fits") as hdus:
        assert classify_origin(hdus[0].header) == ("osp-test-fixture", "1")
    real_dark = frame_file(tmp_path / "real-dark.fits", x.astype(np.int32), "DARK", 120)
    with pytest.raises(OriginError):
        build_master([*darks[:-1], real_dark], config)
    obs_config = config.model_copy(update={"synthetic_test": False})
    with pytest.raises(OriginError):
        build_master(darks, obs_config)
    different = frame_file(
        tmp_path / "other-generated-dark.fits",
        x.astype(np.int32),
        "DARK",
        120,
        **{**MARKERS, "SIMVER": "2"},
    )
    with pytest.raises(CalibrationError, match="heterogeneous"):
        build_master([*darks[:-1], different], config)
    real_light = frame_file(tmp_path / "real-light.fits", (120 + x).astype(float), "LIGHT", 120)
    with pytest.raises(CalibrationError, match="compatible DARK"):
        reduce_exposure(real_light, obs_config, dark_id=dark.id, flat_id=flat.id)
    light = frame_file(
        tmp_path / "synthetic-light.fits", (120 + x).astype(float), "LIGHT", 120, **MARKERS
    )
    result = reduce_exposure(light, config, mode="calibrate", dark_id=dark.id, flat_id=flat.id)
    product = type(light)(result["path"])
    assert validate_product(product)["shape"] == (32, 40)
    assert classify_origin(fits.getheader(product)) == inspect_frame(light).origin
