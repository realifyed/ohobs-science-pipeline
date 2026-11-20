"""Exercise the TAP protocol locally and independent, epoch-shifted matching."""

import io
import json

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
from astropy.wcs import WCS

from ohobs_pipeline import astrometry, gaia
from ohobs_pipeline.config import Astrometry, Gaia
from ohobs_pipeline.quality import Source


def test_auto_gaia_cache_offline_and_epoch(tmp_path, monkeypatch):
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [359.999, -25]
    wcs.wcs.crpix = [51, 51]
    wcs.wcs.cdelt = [-1 / 3600, 1 / 3600]
    points = [(10, 12), (85, 12), (10, 89), (85, 89), (45, 40), (55, 65)]
    x, y = np.array(points).T
    apparent = wcs.pixel_to_world(x, y).icrs
    epoch = Time(2030, format="jyear", scale="tcb")
    original = SkyCoord(apparent.ra, apparent.dec).directional_offset_by(
        270 * u.deg, (2030 - 2016) * 540 * u.mas
    )
    fixture = Table(
        {
            "source_id": np.arange(len(x), dtype=np.int64),
            "ra": original.ra,
            "dec": original.dec,
            "pmra": np.full(len(x), 540) * u.mas / u.yr,
            "pmdec": np.zeros(len(x)) * u.mas / u.yr,
            "ref_epoch": np.full(len(x), 2016.0),
            "ruwe": np.ones(len(x)),
            "duplicated_source": np.zeros(len(x), dtype=bool),
            "phot_g_mean_mag": np.full(len(x), 14.0),
        }
    )
    buffer = io.BytesIO()
    fixture.write(buffer, format="votable")
    queries = []

    def download(adql, _settings):
        queries.append(adql)
        assert "gaiadr3.gaia_source" in adql and "POWER(pmra,2)" in adql and "TOP" in adql
        return buffer.getvalue()

    monkeypatch.setattr(gaia, "_download", download)
    settings = Astrometry(
        gaia=Gaia(enabled=True, allow_network=True, cache_dir=tmp_path / "cache"),
        catalogue_independence_evidence="independent fixture, held-out pixels",
        min_matches=5,
        max_rms_arcsec=0.05,
        min_coverage_fraction=0.25,
    )
    candidate = tmp_path / "wcs.fits"
    fits.PrimaryHDU(header=wcs.to_header()).writeto(candidate)
    sources = [Source(int(a), int(b), 100, 2.5, 0.1, 12, 0) for a, b in points]
    first = astrometry.assess_candidate(candidate, (100, 100), sources, epoch, settings).report
    assert first["status"] == "VERIFIED" and first["rms_arcsec"] < 0.01
    assert sum(sector["inliers"] for sector in first["spatial_half_field_residuals"]) == len(points)
    offline = settings.model_copy(
        update={"gaia": settings.gaia.model_copy(update={"allow_network": False})}
    )
    second = astrometry.assess_candidate(candidate, (100, 100), sources, epoch, offline).report
    assert second == first and len(queries) == 1
    cached = next((tmp_path / "cache").glob("*/reference.ecsv"))
    cached.write_text("corrupted", encoding="utf-8")
    bad = astrometry.assess_candidate(candidate, (100, 100), sources, epoch, offline).report
    assert bad["solve_status"] == "SOLVED" and bad["status"] == "UNVERIFIED"
    assert "checksum" in " ".join(bad["reasons"])


def test_gaia_offline_miss_and_overflow_discard(tmp_path, monkeypatch):
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crpix = [16, 16]
    wcs.wcs.cdelt = [-0.001, 0.001]
    settings = Gaia()
    epoch = Time("2026-01-01")
    with pytest.raises(gaia.GaiaError, match="offline cache"):
        gaia.reference(wcs, (32, 32), epoch, settings, tmp_path)
    body = (
        '<?xml version="1.0"?><VOTABLE version="1.3" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">'
        '<RESOURCE type="results"><INFO name="QUERY_STATUS" value="OVERFLOW"/></RESOURCE></VOTABLE>'
    )
    monkeypatch.setattr(gaia, "_download", lambda *_: body.encode())
    with pytest.raises(gaia.GaiaError, match="truncated"):
        gaia.reference(
            wcs, (32, 32), epoch, settings.model_copy(update={"allow_network": True}), tmp_path
        )
    assert not list(tmp_path.glob("*/manifest.json"))


def test_event_records_allow_fields_without_exception_payload(tmp_path):
    from ohobs_pipeline.events import Events

    events = Events(tmp_path, "batch", job_id="j")
    events.observation_id = "sha256"
    events.emit("stage_failed", stage="ASTROMETRY", error_type="GaiaError")
    record = json.loads(events.path.read_text(encoding="utf-8"))
    assert record["job_id"] == "j" and record["observation_id"] == "sha256"
    assert "reason" not in record and isinstance(record["elapsed_s"], float)


def test_independent_expectation_preserves_science_and_changes_variance(dataset, tmp_path):
    from ohobs_pipeline.ingest import inspect_frame
    from ohobs_pipeline.pipeline import reduce_exposure
    from ohobs_pipeline.products import read_calibrated

    light = dataset["light"]
    config = dataset["config"]
    frame = inspect_frame(light, config)
    expected = tmp_path / "independent.fits"
    fits.PrimaryHDU(
        np.asarray(dataset["truth"] * dataset["response"], dtype=float),
        fits.Header({"OBS_ID": frame.sha256, "OSSIGNAL": "INDEPENDENT", "BUNIT": "adu"}),
    ).writeto(expected, checksum=True)
    independent = config.model_validate(
        {
            **config.model_dump(),
            "photon_expectation": expected,
            "photon_expectation_evidence": "known simulator sky and response, independent of readout",
        }
    )
    from pathlib import Path

    a = reduce_exposure(light, config, mode="calibrate")
    b = reduce_exposure(light, independent, mode="calibrate")
    assert a["id"] != b["id"]
    one, two = (read_calibrated(Path(item["path"])) for item in (a, b))
    np.testing.assert_array_equal(one.science, two.science)
    np.testing.assert_array_equal(one.dq, two.dq)
    assert not np.allclose(one.variance, two.variance, equal_nan=True)
