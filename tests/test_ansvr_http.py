"""Contract tests for the installed ANSVR 0.22 protocol."""

import io
import json

import numpy as np
import pytest
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from pydantic import ValidationError

from ohobs_pipeline import ansvr_http
from ohobs_pipeline.astrometry import solve
from ohobs_pipeline.config import Astrometry
from ohobs_pipeline.quality import Source


def test_ansvr_http_fits_wcs_and_holdout(tmp_path, monkeypatch):
    truth = WCS(naxis=2)
    truth.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    truth.wcs.crpix = [50.5, 40.5]
    truth.wcs.crval = [118, -24]
    truth.wcs.cdelt = [-1 / 3600, 1 / 3600]
    buffer = io.BytesIO()
    fits.PrimaryHDU(header=truth.to_header()).writeto(buffer)
    responses = iter(
        [
            ("/api/login", {"session": "42", "status": "success"}),
            ("/api/upload/", {"subid": 42, "status": "success"}),
            ("/api/submissions/42", {"jobs": [], "processing_finished": "0"}),
            ("/api/submissions/42", {"jobs": [42], "processing_finished": "1"}),
            ("/api/jobs/42", {"status": "success"}),
            ("/wcs_file/42", buffer.getvalue()),
        ]
    )
    sources = [Source(10 + i, 20 + i, i, 3, 0.2, None, 0) for i in range(12)]

    def fake_request(self, path, body=None, content_type=None):
        expect, response = next(responses)
        assert path == expect
        if path == "/api/upload/":
            assert content_type.startswith("multipart/form-data; boundary=")
            assert b"Content-Type: application/octet-stream\r\n" in body
            lines = body.decode("ascii").splitlines()
            upload = json.loads(next(line for line in lines if '"allow_commercial_use"' in line))
            assert upload["image_width"] == 100 and upload["image_height"] == 80
            assert upload["scale_type"] == "ul"
            assert (upload["scale_lower"], upload["scale_upper"]) == (0.95, 1.19)
            assert (upload["center_ra"], upload["center_dec"]) == (118, -24)
            xy = [tuple(map(float, line.split())) for line in lines if line[:1].isdigit()]
            assert xy == [(s.x + 1, s.y + 1) for s in reversed(sources) if s.flux % 3]
        elif path.startswith("/wcs_file"):
            assert body is None
        else:
            assert isinstance(body, bytes)
        return response if isinstance(response, bytes) else json.dumps(response).encode()

    monkeypatch.setattr(ansvr_http.Client, "request", fake_request)
    monkeypatch.setattr(ansvr_http, "sleep", lambda _: None)
    config = Astrometry(
        backend="ansvr_http",
        ansvr_url="http://127.0.0.1:8080",
        scale_min=0.95,
        scale_max=1.19,
        pointing_radius_deg=2,
    )
    result = solve(sources, (80, 100), Time("2026-05-03"), config, tmp_path, (118, -24))
    assert next(responses, None) is None
    assert result.report["status"] == "UNVERIFIED"
    assert result.report["holdout_count"] == 4
    assert result.report["fitting_candidates"] == 8
    assert result.report["solve_duration_s"] >= 0
    np.testing.assert_allclose(result.report["scale_arcsec_px"], [1, 1])
    report = json.loads((tmp_path / "http-0.json").read_bytes())
    assert report["state"] == "WCS_RECEIVED"


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8080",
        "http://example.org:8080",
        "http://127.0.0.1:8080/api",
        "http://127.0.0.1",
    ],
)
def test_ansvr_http_requires_local_origin(url):
    with pytest.raises(ValidationError, match="loopback"):
        Astrometry(backend="ansvr_http", ansvr_url=url)


def test_ansvr_http_records_failed_job(tmp_path, monkeypatch):
    replies = iter(
        [
            {"session": "1"},
            {"status": "success", "subid": "1"},
            {"jobs": ["1"], "processing_finished": 1},
            {"status": "failure"},
        ]
    )
    monkeypatch.setattr(ansvr_http.Client, "request", lambda *a: json.dumps(next(replies)).encode())
    cfg = Astrometry(backend="ansvr_http", ansvr_url="http://127.0.0.1:8080")
    points = [Source(10 + i, 20 + i, i, 3, 0.2, None, 0) for i in range(8)]
    path = tmp_path / "failed.json"
    with pytest.raises(ansvr_http.AnsvrError, match="reported solve failure"):
        ansvr_http.solve_centroids(cfg, points, (80, 100), None, path)
    assert json.loads(path.read_bytes())["state"] == "JOB"
