from pathlib import Path

import numpy as np
import pytest
from astropy.table import Table
from astropy.time import Time
from astropy.wcs import WCS

from ohobs_pipeline.astrometry import AstrometryError, load_candidate, validate_catalogue
from ohobs_pipeline.config import Astrometry
from ohobs_pipeline.integrity import publish_directory
from ohobs_pipeline.jobs import create_job, job_info, run_job
from ohobs_pipeline.quality import Source


def test_held_out_wcs_across_ra_wrap(tmp_path):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [359.999, 78]
    w.wcs.crpix = [51.0, 41.0]
    w.wcs.cd = [[-0.0003, 0.00001], [0.00001, 0.0003]]
    shape = 80, 100
    settings = Astrometry(
        min_matches=5,
        max_rms_arcsec=0.15,
        catalogue_independence_evidence="independent synthetic truth",
        scale_min=0.9,
        scale_max=1.2,
    )
    candidate = load_candidate(w.to_header(), shape, settings)
    time = Time(2024, format="jyear", scale="tcb")
    px, py = np.meshgrid([10, 40, 90], [10, 35, 70])
    px, py = px.ravel(), py.ravel()
    coordinates = w.pixel_to_world(px, py)
    assert coordinates.ra.deg.min() < 1
    import astropy.units as u

    prior = coordinates.directional_offset_by(270 * u.deg, 2.4 * u.arcsec)
    table = Table(
        {
            "ra": prior.ra.deg,
            "dec": prior.dec.deg,
            "source_id": range(len(px)),
            "pmra": [300.0] * len(px),
            "pmdec": [0.0] * len(px),
            "ref_epoch": [2016.0] * len(px),
        }
    )
    catalogue = tmp_path / "held.ecsv"
    table.write(catalogue)
    held = [Source(float(x), float(y), 100, 3, 0.15, None, 0) for x, y in zip(px, py, strict=True)]
    report = validate_catalogue(candidate, held, catalogue, time, shape, settings)
    assert report["status"] == "VERIFIED"
    assert report["rms_arcsec"] < 0.001
    w.wcs.crval = [359.8, 78]
    with pytest.raises(AstrometryError, match="no unambiguous"):
        validate_catalogue(w, held, catalogue, time, shape, settings)


def test_atomic_failure(tmp_path):
    target = tmp_path / "data"
    with pytest.raises(RuntimeError), publish_directory(target) as stage:
        (stage / "science.fits").write_bytes(b"partial data")
        raise RuntimeError("interruption")
    assert not target.exists()
    assert not list(tmp_path.glob(".osp-*"))


def test_batch_resume(dataset, monkeypatch):
    import shutil

    source = dataset["light"].parent
    shutil.copyfile(dataset["light"], source / "same bytes, second copy.fits")
    # Child workers must import the same source tree when run before installation.
    monkeypatch.setenv("PYTHONPATH", str(Path.cwd() / "src"))
    result = create_job(source, dataset["config_path"])
    assert result["counts"] == {"PARTIAL": 2}
    assert len({frame["outcome"]["path"] for frame in result["frames"]}) == 1
    again = run_job(dataset["config"].work_dir, result["id"])
    assert again == result
    work = dataset["config"].work_dir
    audit = job_info(work, result["id"], verify_products=True)
    assert audit["product_integrity"] == {"VERIFIED": 2, "FAILED": 0}
    product = Path(result["frames"][0]["outcome"]["path"])
    product.rename(product.with_suffix(".isolated"))
    audit = job_info(work, result["id"], verify_products=True)
    assert audit["product_integrity"] == {"VERIFIED": 0, "FAILED": 2}
    assert job_info(work, result["id"]) == result


def test_checkpoint_recovers_inflight_and_changed_input(dataset, monkeypatch):
    from contextlib import closing

    from ohobs_pipeline.jobs import connect

    source = dataset["light"].parent
    monkeypatch.setenv("PYTHONPATH", str(Path.cwd() / "src"))
    first = create_job(source, dataset["config_path"])
    job = first["id"]
    work = dataset["config"].work_dir
    with closing(connect(work)) as db, db:
        db.execute("UPDATE task SET state='VALIDATING',outcome=NULL WHERE job=?", (job,))
    restored = run_job(work, job)
    assert restored["counts"] == {"PARTIAL": 1}
    assert restored["frames"][0]["outcome"]["reused"]
    with closing(connect(work)) as db, db:
        db.execute("UPDATE task SET state='FAILED',outcome=NULL WHERE job=?", (job,))
    with dataset["light"].open("ab") as raw:
        raw.write(b"changed")
    rejected = run_job(work, job, retry=True)
    assert rejected["counts"] == {"QUARANTINED": 1}


def test_wcs_with_sip_preserves_origin_and_parity():
    from astropy.wcs import Sip

    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN-SIP", "DEC--TAN-SIP"]
    wcs.wcs.crval = [25.0, -40.0]
    wcs.wcs.crpix = [50.0, 35.0]
    wcs.wcs.cdelt = [-0.00025, 0.00028]
    a, b = np.zeros((3, 3)), np.zeros((3, 3))
    a[2, 0], b[0, 2] = 5.0e-5, -6.0e-5
    wcs.sip = Sip(a, b, None, None, wcs.wcs.crpix)
    accepted = load_candidate(
        wcs.to_header(relax=True), (70, 100), Astrometry(scale_min=0.8, scale_max=1.1)
    )
    assert accepted.sip.a_order == 2
    assert np.linalg.det(accepted.pixel_scale_matrix) < 0
    np.testing.assert_allclose(accepted.pixel_to_world_values(49.0, 34.0), [25.0, -40.0])


@pytest.mark.parametrize("backend", ["astrometry_net", "ansvr"])
def test_solver_adapter_holds_out_detections_and_retries(tmp_path, monkeypatch, backend):
    import subprocess

    import astropy.units as u
    from astropy.io import fits

    from ohobs_pipeline import astrometry

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [123.0, -30.0]
    w.wcs.crpix = [51.0, 51.0]
    w.wcs.cdelt = [-0.0003, 0.0003]
    xy = [(x, y) for y in (10, 30, 70, 90) for x in (10, 35, 60, 85)]
    sources = [Source(float(x), float(y), 100 - i, 3, 0.2, None, 0) for i, (x, y) in enumerate(xy)]
    held = np.array(xy[::3])
    sky = w.pixel_to_world(*held.T)
    catalogue = tmp_path / "catalogue.ecsv"
    Table(
        {
            "source_id": list(range(len(held))),
            "ra": sky.ra.to_value(u.deg),
            "dec": sky.dec.to_value(u.deg),
            "pmra": np.zeros(len(held)),
            "pmdec": np.zeros(len(held)),
            "ref_epoch": np.full(len(held), 2016.0),
        }
    ).write(catalogue)

    monkeypatch.setattr(astrometry.shutil, "which", lambda _: "mock-solve-field")
    settings = {"backend": backend}
    if backend == "ansvr":
        root = tmp_path / "ANSVR installation"
        settings.update(ansvr_root=root)
        for path in astrometry.solver_files(Astrometry.model_validate(settings)).values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
    work = tmp_path / "solver with spaces"
    calls = []

    def fake_solver(args, **kwargs):
        if backend == "ansvr" and args[0].endswith("cygpath.exe"):
            assert args[1:] == ["-u", "--", str(work)]
            return subprocess.CompletedProcess(args, 0, b"/cygdrive/c/solver with spaces\n")
        calls.append(args)
        if backend == "ansvr":
            assert args[0].endswith("bash.exe")
            assert args[-1] == "/cygdrive/c/solver with spaces/sources.xyls"
            assert '"$@"' in args[4]
        table = Table.read(work / "sources.xyls", format="fits")
        np.testing.assert_array_equal(
            np.column_stack((table["X"], table["Y"])),
            np.array([point for i, point in enumerate(xy) if i % 3]) + 1,
        )
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        result = work / Path(args[args.index("--wcs") + 1]).name
        fits.PrimaryHDU(header=w.to_header()).writeto(result)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(astrometry.subprocess, "run", fake_solver)
    result = astrometry.solve(
        sources,
        (100, 100),
        Time(2024.0, format="jyear", scale="tcb"),
        Astrometry.model_validate(
            {
                **settings,
                "attempts": 2,
                "catalogue": catalogue,
                "min_matches": 5,
                "max_rms_arcsec": 0.05,
                "pointing_radius_deg": 3,
                "catalogue_independence_evidence": "synthetic fixture",
            }
        ),
        work,
        pointing=(123.0, -30.0),
    )
    assert result.report["status"] == "VERIFIED"
    assert result.report["backend"] == backend
    assert result.report["holdout_count"] == len(held)
    assert "--ra" in calls[0] and "--ra" not in calls[1]


def test_actual_crashed_worker_can_recover(dataset, monkeypatch):
    import subprocess
    import sys

    from ohobs_pipeline import jobs

    monkeypatch.setenv("PYTHONPATH", str(Path.cwd() / "src"))
    real = subprocess.run
    counter = 0

    def inject_once(*args, **kwargs):
        nonlocal counter
        counter += 1
        if counter == 1:
            return real([sys.executable, "-c", "import os; os._exit(28)"], **kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(jobs.subprocess, "run", inject_once)
    first = jobs.create_job(dataset["light"].parent, dataset["config_path"])
    assert first["counts"] == {"FAILED": 1}
    assert first["frames"][0]["outcome"]["returncode"] == 28
    second = jobs.run_job(dataset["config"].work_dir, first["id"], retry=True)
    assert second["counts"] == {"PARTIAL": 1}
    assert Path(second["frames"][0]["outcome"]["path"]).exists()


def test_catalogue_bytes_change_batch_identity(dataset):
    import yaml

    config_path = dataset["config_path"]
    catalogue = config_path.parent / "reference.ecsv"
    catalogue.write_text("first catalogue snapshot", encoding="utf-8")
    doc = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    doc["astrometry"]["catalogue"] = catalogue.name
    config_path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    before = create_job(dataset["light"].parent, config_path, dry_run=True)
    catalogue.write_text("changed catalogue snapshot", encoding="utf-8")
    after = create_job(dataset["light"].parent, config_path, dry_run=True)
    assert before["id"] != after["id"]
