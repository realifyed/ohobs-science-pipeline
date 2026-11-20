"""Portable paths and public observational configuration contracts."""

from pathlib import Path

from ohobs_pipeline.config import load_config
from ohobs_pipeline.jobs import discover


def test_configuration_paths_follow_yaml_not_working_directory(tmp_path, monkeypatch):
    folder = tmp_path / "observatory with spaces"
    folder.mkdir()
    configuration = folder / "observatory.yaml"
    configuration.write_text(
        "node: EXAMPLE\nwork_dir: products\nraw_dir: observations\n"
        "calibration_dir: calibration\nastrometry:\n  catalogue: reference.ecsv\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    config = load_config(configuration)
    assert config.work_dir == folder / "products"
    assert config.raw_dir == folder / "observations"
    assert config.calibration_dir == folder / "calibration"
    assert config.astrometry.catalogue == folder / "reference.ecsv"


def test_discovery_handles_mixed_case_extensions_and_nested_paths(tmp_path):
    nested = tmp_path / "night with spaces"
    nested.mkdir()
    for name in ("b.FITS", "a.fit", "c.FtS", "ignore.fits.tmp", "notes.txt"):
        (nested / name).touch()
    assert [path.name for path in discover(tmp_path)] == ["a.fit", "b.FITS", "c.FtS"]
    assert all(path.is_absolute() for path in discover(tmp_path))


def test_generic_example_has_no_invented_detector_measurements():
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "configs/examples/observatory.yaml")
    assert config.synthetic_test is False
    assert config.detector.gain_e_per_adu is None
    assert config.detector.read_noise_e is None
    assert config.detector.saturation is None
    assert config.detector.linear_max is None
    assert config.overrides == {}
    assert config.astrometry.online.authorize_upload is False
