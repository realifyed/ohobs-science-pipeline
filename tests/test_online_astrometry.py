"""Nova contract, privacy, retry and recovery checks with synthetic data."""

import io
import json
from dataclasses import dataclass, field
from http.client import HTTPResponse
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs
from uuid import uuid4

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
from astropy.wcs import WCS
from pydantic import ValidationError

from ohobs_pipeline import astrometry
from ohobs_pipeline import online_astrometry as nova
from ohobs_pipeline.config import Astrometry, Online, astrometry_override
from ohobs_pipeline.quality import Source


def sources():
    return [
        Source(x, y, 10 + index, 3, 0.2, None, 0)
        for index, (x, y) in enumerate((x, y) for x in (5, 22, 46, 78) for y in (8, 25, 62, 78))
    ]


def candidate():
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crpix = [50.5, 40.5]
    w.wcs.crval = [118, -24]
    w.wcs.cdelt = [-1 / 3600, 1 / 3600]
    f = io.BytesIO()
    fits.PrimaryHDU(header=w.to_header()).writeto(f)
    return f.getvalue()


@dataclass
class Server:
    key: str
    token: str = field(default_factory=lambda: uuid4().hex)
    accepted: int = 0
    polls: int = 0
    logins: int = 0
    paths: list = field(default_factory=list)
    requests: list = field(default_factory=list)
    actions: dict = field(default_factory=dict)
    terminal: str = "success"

    def dispatch(self, method, path, body, headers):
        self.paths.append(path)
        data = None
        if body and headers.get("Content-Type", "").startswith("application/x-www"):
            data = json.loads(parse_qs(body.decode())["request-json"][0])
        self.requests.append((path, data))
        if queued := self.actions.get(path):
            action = queued.pop(0)
            if isinstance(action, Exception):
                raise action
            return action
        if path == "/api/login":
            self.logins += 1
            assert method == "POST" and data == {"apikey": self.key}
            return 200, {"status": "success", "session": self.token}
        if path == "/api/url_upload":
            assert method == "POST" and data["session"] == self.token
            self.accepted += 1
            return 200, {"status": "success", "subid": 73}
        if path == "/api/upload":
            self.accepted += 1
            boundary = headers["Content-Type"].split("boundary=")[1].encode()
            parts = body.split(b"--" + boundary)
            meta = json.loads(parts[1].split(b"\r\n\r\n")[1])
            assert meta["session"] == self.token and meta["publicly_visible"] == "n"
            image = parts[2].split(b"\r\n\r\n", 1)[1][:-2]
            with fits.open(io.BytesIO(image)) as hdus:
                assert hdus[0].data.shape == (80, 100)
                assert "OBJECT" not in hdus[0].header
            return 200, {"status": "success", "subid": 73}
        assert method == "GET"
        if path == "/api/submissions/73":
            self.polls += 1
            return 200, {"jobs": [None] if self.polls == 1 else [82], "processing_finished": "date"}
        if path == "/api/jobs/82":
            return 200, {"status": self.terminal}
        if path == "/api/jobs/82/calibration/":
            return 200, {"ra": 118.0, "dec": -24.0, "pixscale": 1.0, "session": self.token}
        if path == "/wcs_file/82":
            return 200, candidate()
        pytest.fail(f"unexpected mock request path {path}")


@pytest.fixture
def server(monkeypatch):
    service = Server(uuid4().hex)
    monkeypatch.setenv(nova.KEY_ENV, service.key)

    class ResponseSocket:
        def __init__(self, data):
            self.data = data

        def makefile(self, *args, **kwargs):
            return io.BytesIO(self.data)

    class InMemoryConnection:
        def __init__(self, host, *, timeout, context):
            assert host == "nova.astrometry.net"
            assert context.check_hostname and context.verify_mode

        def request(self, method, path, body, headers):
            status, value = service.dispatch(method, path, body, headers)
            payload = value if isinstance(value, bytes) else json.dumps(value).encode()
            raw = (
                f"HTTP/1.1 {status} Test\r\nContent-Length: {len(payload)}\r\n"
                "Retry-After: 1\r\nLocation: https://example.org/\r\n\r\n"
            ).encode() + payload
            self.response = HTTPResponse(ResponseSocket(raw))
            self.response.begin()

        def getresponse(self):
            return self.response

        def close(self):
            pass

    monkeypatch.setattr(nova.http.client, "HTTPSConnection", InMemoryConnection)
    monkeypatch.setattr(nova.Client, "pause", lambda self, delay: self.remaining())
    return service


def config(**kwargs):
    return Astrometry(
        backend="online",
        scale_min=0.95,
        scale_max=1.19,
        pointing_radius_deg=2,
        online=Online(authorize_upload=True, **kwargs),
    )


def test_online_lifecycle_reuses_candidate_and_keeps_secrets_out(tmp_path, server):
    args = (
        sources(),
        (80, 100),
        Time("2026-05-03"),
        config(),
        tmp_path / "diagnostics",
        (118, -24),
    )
    root = tmp_path / "receipts"
    first = astrometry.solve(*args, online_root=root)
    assert first.report["status"] == "UNVERIFIED"
    assert first.report["solve_status"] == "SOLVED"
    assert first.report["submission_id"] == "73" and first.report["job_id"] == "82"
    assert first.report["center_ra_deg"] == pytest.approx(118)
    expected = sorted([s for i, s in enumerate(args[0]) if i % 3], key=lambda s: -s.flux)
    sent = next(fields for path, fields in server.requests if path == "/api/url_upload")
    assert sent["x"] == [s.x + 1 for s in expected]
    assert sent["y"] == [s.y + 1 for s in expected]
    assert sent["image_width"] == 100 and sent["image_height"] == 80
    assert sent["scale_lower"] == 0.95 and sent["center_ra"] == 118
    assert sent["publicly_visible"] == "n"
    assert (
        astrometry.solve(*args, online_root=root).report["receipt_id"] == first.report["receipt_id"]
    )
    assert server.logins == server.accepted == 1
    for path in tmp_path.rglob("*.json"):
        value = path.read_text()
        assert server.key not in value and server.token not in value


def test_timeout_can_resume_without_resubmitting(tmp_path, server, monkeypatch):
    def expire(self, delay):
        raise nova.NovaError("TIMEOUT", "local deadline")

    with monkeypatch.context() as m:
        m.setattr(nova.Client, "pause", expire)
        with pytest.raises(nova.NovaError, match="Receipt") as err:
            nova.solve(config(), tmp_path, sources(), (80, 100), None, None, "source_list")
    assert err.value.pending and err.value.category == "TIMEOUT"
    receipt = next(tmp_path.glob("*.json"))
    assert json.loads(receipt.read_bytes())["state"] == "PENDING"
    assert nova.status(config().online, tmp_path, receipt.stem, cancel=True)["local_wait_cancelled"]
    result = nova.status(config().online, tmp_path, receipt.stem, wait=True)
    assert result["state"] == "SOLVED" and Path(result["wcs_path"]).is_file()
    assert server.accepted == 1


def test_ambiguous_upload_never_replayed(tmp_path, server):
    server.actions["/api/url_upload"] = [ConnectionResetError()]
    for expected in ["NETWORK", "UPLOAD_UNKNOWN"]:
        with pytest.raises(nova.NovaError) as err:
            nova.solve(config(), tmp_path, sources(), (80, 100), None, None, "source_list")
        assert err.value.category == expected and err.value.pending
    assert server.paths.count("/api/url_upload") == 1
    receipt = next(tmp_path.glob("*.json"))
    assert (
        nova.status(config().online, tmp_path, receipt.stem, abandon=True)["state"] == "ABANDONED"
    )


def test_authentication_and_rate_limit_redact_and_refresh(tmp_path, server, monkeypatch):
    server.actions["/api/login"] = [(200, {"status": "error", "errormessage": server.key})]
    with pytest.raises(nova.NovaError, match="authentication was rejected") as err:
        astrometry.probe_solver(config())
    assert server.key not in str(err.value)
    monkeypatch.delenv(nova.KEY_ENV)
    with pytest.raises(nova.NovaError, match=nova.KEY_ENV):
        astrometry.probe_solver(config())
    monkeypatch.setenv(nova.KEY_ENV, server.key)
    server.actions["/api/url_upload"] = [
        (429, {}),
        (
            200,
            {
                "status": "error",
                "errormessage": f"expired session {server.token}",
            },
        ),
    ]
    nova.solve(config(), tmp_path, sources(), (80, 100), None, None, "source_list")
    assert server.logins == 2 and server.accepted == 1


def test_auto_permission_and_image_fallback(tmp_path, server, monkeypatch):
    monkeypatch.setattr(
        astrometry.ansvr_http,
        "solve_centroids",
        lambda *a: (_ for _ in ()).throw(astrometry.ansvr_http.AnsvrError("local unavailable")),
    )
    cfg = Astrometry(backend="auto", fallback_enabled=True)
    args = (sources(), (80, 100), Time("2026-05-03"), cfg, tmp_path / "auto")
    with pytest.raises(nova.NovaError, match="authorization"):
        astrometry.solve(*args)
    assert server.paths == []
    assert astrometry_override(cfg, "local").local_endpoint.endswith(":8080")
    fallback = config(upload_mode="image_fallback", authorize_image_upload=True)
    result = astrometry.solve(
        [], (80, 100), args[2], fallback, tmp_path / "image", image=np.ones((80, 100))
    )
    assert "/api/upload" in server.paths and "/api/url_upload" not in server.paths
    assert result.report["status"] == "UNVERIFIED" and not result.report["independent_holdout"]


def test_solver_failure_and_invalid_wcs_are_distinct(tmp_path, server):
    server.terminal = "failure"
    with pytest.raises(nova.NovaError) as err:
        nova.solve(config(), tmp_path / "failed", sources(), (80, 100), None, None, "source_list")
    assert err.value.category == "SOLVER_FAILED" and not err.value.pending
    server.terminal = "success"
    buffer = io.BytesIO()
    fits.PrimaryHDU().writeto(buffer)
    server.actions["/wcs_file/82"] = [(200, buffer.getvalue())]
    with pytest.raises(nova.NovaError) as err:
        astrometry.solve(sources(), (80, 100), Time("2026-05-03"), config(), tmp_path / "bad")
    assert err.value.category == "INVALID_WCS"


def test_endpoint_redirect_is_never_followed(server):
    with pytest.raises(ValidationError, match="nova.astrometry.net"):
        Online.model_validate({"endpoint": "https://example.org"})
    server.actions["/api/login"] = [(302, {})]
    with pytest.raises(nova.HttpFailure, match="302"):
        astrometry.probe_solver(config())
    assert server.paths == ["/api/login"]


def test_private_ansvr_host_requires_explicit_policy():
    private = "http://192.168.1.50:8080"
    with pytest.raises(ValidationError, match="loopback"):
        Astrometry(backend="local", ansvr_url=private)
    assert (
        Astrometry(backend="local", ansvr_url=private, allow_private_ansvr=True).local_endpoint
        == private
    )
    with pytest.raises(ValidationError, match="loopback"):
        Astrometry(backend="local", ansvr_url="http://example.org:8080", allow_private_ansvr=True)


def test_cli_solve_status_and_verify(tmp_path, server, monkeypatch, capsys):
    from ohobs_pipeline import cli

    image = np.ones((80, 100))
    light = tmp_path / "light.fits"
    fits.PrimaryHDU(image).writeto(light)
    monkeypatch.setattr(
        cli,
        "_raw_sources",
        lambda *_: (
            SimpleNamespace(
                shape=image.shape,
                path=light,
                sha256=cli.digest(light),
                midpoint="2026-05-03",
                time_scale="utc",
                header={},
            ),
            image,
            {},
            sources(),
        ),
    )
    settings = tmp_path / "config.json"
    settings.write_text(json.dumps({"node": "TEST", "work_dir": "work"}), encoding="utf-8")
    common = ["--config", str(settings)]
    output = tmp_path / "solve"
    assert (
        cli.main(
            [
                "astrometry",
                "solve",
                str(light),
                "--backend",
                "online",
                "--allow-online",
                "--output",
                str(output),
                *common,
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    receipt = result["receipt_id"]
    assert cli.main(["astrometry", "status", receipt, *common]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "SOLVED"
    assert (
        cli.main(
            [
                "astrometry",
                "verify",
                str(light),
                "--wcs",
                str(output / "candidate.wcs"),
                "--solve-report",
                str(output / "validation.json"),
                *common,
            ]
        )
        == 1
    )
    verification = json.loads(capsys.readouterr().out)
    assert verification["status"] == "UNVERIFIED" and verification["solve_status"] == "SOLVED"
    assert "independent image-source holdout is not established" not in verification["reasons"]
    assert server.accepted == 1


def test_online_uses_shared_gaia_acceptance(tmp_path, server):
    points = sources()
    xy = np.asarray([(s.x, s.y) for s in points[::3]])
    header = fits.getheader(io.BytesIO(candidate()))
    del header["NAXIS"]
    wcs = WCS(header)
    ra, dec = wcs.pixel_to_world_values(xy[:, 0], xy[:, 1])
    catalogue = tmp_path / "reference.ecsv"
    Table(
        {
            "source_id": np.arange(len(xy)),
            "ra": ra,
            "dec": dec,
            "pmra": np.zeros(len(xy)),
            "pmdec": np.zeros(len(xy)),
            "ref_epoch": np.full(len(xy), 2016.0),
        }
    ).write(catalogue, format="ascii.ecsv")
    settings = Astrometry(
        backend="online",
        catalogue=catalogue,
        min_matches=4,
        max_rms_arcsec=0.05,
        online=Online(
            authorize_upload=True, catalogue_independence_evidence="synthetic independent reference"
        ),
    )
    solved = astrometry.solve(points, (80, 100), Time("2026-05-03"), settings, tmp_path / "online")
    assert solved.report["status"] == "VERIFIED"
    assert solved.report["match_count"] == len(xy)
    assert solved.report["rms_arcsec"] < 0.05


def test_persistent_admission_limits_new_submissions(tmp_path, server, monkeypatch):
    (tmp_path / "existing.json").write_text('{"state":"PENDING"}')

    def expire(self, delay):
        raise nova.NovaError("TIMEOUT", "local deadline")

    monkeypatch.setattr(nova.Client, "pause", expire)
    with pytest.raises(nova.NovaError) as err:
        nova.solve(
            config(max_concurrent_jobs=1), tmp_path, sources(), (80, 100), None, None, "source_list"
        )
    assert err.value.category == "TIMEOUT"
    assert server.logins == 0 and server.accepted == 0


def test_online_http_server_probe_when_loopback_available(monkeypatch):
    from http.client import HTTPConnection
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socket import create_connection
    from threading import Thread

    key, session = uuid4().hex, uuid4().hex

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            payload = json.loads(parse_qs(body)["request-json"][0])
            if self.path != "/api/login" or payload != {"apikey": key}:
                self.send_error(403)
                return
            response = json.dumps({"status": "success", "session": session}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    try:
        service = HTTPServer(("127.0.0.1", 0), Handler)
    except OSError as exc:
        pytest.skip(f"local HTTP listener is unavailable: {exc}")
    with service:
        try:
            with create_connection(("127.0.0.1", service.server_port), timeout=1):
                pass
        except PermissionError as exc:
            pytest.skip(f"local HTTP connection is blocked: {exc}")
        thread = Thread(target=service.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setenv(nova.KEY_ENV, key)
        monkeypatch.setattr(
            nova.http.client,
            "HTTPSConnection",
            lambda host, timeout, context: HTTPConnection(
                "127.0.0.1", service.server_port, timeout=timeout
            ),
        )
        try:
            assert astrometry.probe_solver(config())["status"] == "AVAILABLE"
        finally:
            service.shutdown()
            thread.join(timeout=5)
