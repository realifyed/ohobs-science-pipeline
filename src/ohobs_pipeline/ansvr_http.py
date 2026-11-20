"""Local ANSVR 0.22 protocol for centroid lists and FITS WCS downloads."""

import http.client
import json
import math
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from .config import Astrometry
from .integrity import write_json
from .quality import Source


class AnsvrError(ValueError):
    """An ANSVR request or solve did not complete successfully."""


class Client:
    def __init__(self, settings: Astrometry):
        assert settings.ansvr_url is not None
        self.endpoint = urlsplit(settings.ansvr_url)
        self.deadline = monotonic() + settings.timeout_s

    def remaining(self) -> float:
        seconds = self.deadline - monotonic()
        if seconds <= 0:
            raise AnsvrError("ANSVR HTTP deadline expired")
        return seconds

    def request(
        self, path: str, body: bytes | None = None, content_type: str | None = None
    ) -> bytes:
        # Explicit HTTP connection avoids environment proxies and redirect following.
        conn = http.client.HTTPConnection(
            self.endpoint.hostname or "127.0.0.1", self.endpoint.port, timeout=self.remaining()
        )
        headers = {"Connection": "close"}
        if content_type:
            headers["Content-Type"] = content_type
        try:
            conn.request("GET" if body is None else "POST", path, body, headers)
            with conn.getresponse() as response:
                if response.status != 200:
                    raise AnsvrError(f"ANSVR {path} returned HTTP {response.status}")
                limit = 1024 * 1024
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise AnsvrError(f"ANSVR {path} response exceeds 1 MiB")
                self.remaining()
                return data
        except (OSError, http.client.HTTPException) as exc:
            raise AnsvrError(f"ANSVR HTTP {self.endpoint.netloc}{path}: {exc}") from exc
        finally:
            conn.close()

    def json(self, path: str, body: bytes = b"", content_type: str | None = None) -> dict:
        try:
            result = json.loads(self.request(path, body, content_type))
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise AnsvrError(f"ANSVR {path} returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise AnsvrError(f"ANSVR {path} returned a non-object JSON response")
        return result

    def login(self) -> str:
        response = self.json(
            "/api/login",
            urlencode({"request-json": '{"apikey":""}'}).encode("ascii"),
            "application/x-www-form-urlencoded",
        )
        if response.get("status") not in (None, "success"):
            raise AnsvrError("ANSVR login failed")
        return _id(response.get("session"), "session")


def _id(value: object, label: str) -> str:
    identifier = str(value)
    if not (1 <= len(identifier) <= 32 and identifier.isascii() and identifier.isdecimal()):
        raise AnsvrError(f"ANSVR returned an invalid {label} identifier")
    return identifier


def solve_centroids(
    settings: Astrometry,
    points: list[Source],
    shape: tuple[int, int],
    pointing: tuple[float, float] | None,
    transcript: Path,
) -> bytes:
    """Submit only fitting centroids. Download WCS before any result cleanup."""
    started = monotonic()
    client = Client(settings)
    h, w = shape
    status: dict = {"endpoint": settings.ansvr_url, "state": "LOGIN", "centroids": len(points)}
    try:
        args: dict = {
            "session": client.login(),
            "allow_commercial_use": "d",
            "allow_modifications": "d",
            "publicly_visible": "n",
            "image_width": w,
            "image_height": h,
        }
        if settings.scale_min is not None and settings.scale_max is not None:
            args.update(
                scale_units="arcsecperpix",
                scale_type="ul",
                scale_lower=settings.scale_min,
                scale_upper=settings.scale_max,
            )
        if pointing is not None and settings.pointing_radius_deg is not None:
            ra, dec = pointing
            if math.isfinite(ra) and math.isfinite(dec) and -90 <= dec <= 90:
                args.update(center_ra=ra % 360, center_dec=dec, radius=settings.pointing_radius_deg)
        boundary = uuid4().hex
        # 0.22 detects the request JSON by the allow_commercial_use field and
        # detects the ASCII XY list in an octet-stream multipart part.
        xy = "".join(
            f"{s.x + 1:.8f} {s.y + 1:.8f}\n"
            for s in sorted(points, key=lambda source: source.flux, reverse=True)
            if 0 <= s.x < w and 0 <= s.y < h
        )
        if xy.count("\n") < 6:
            raise AnsvrError("insufficient in-bounds ANSVR centroids")
        payload = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="request-json"\r\n\r\n'
            f"{json.dumps(args, allow_nan=False)}\r\n"
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="sources.txt"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n{xy}\r\n--{boundary}--\r\n"
        ).encode("ascii")
        status.update(state="UPLOAD", scale_arcsec_px=[settings.scale_min, settings.scale_max])
        upload = client.json("/api/upload/", payload, f"multipart/form-data; boundary={boundary}")
        if upload.get("status") != "success":
            raise AnsvrError("ANSVR refused the centroid upload")
        submission = _id(upload.get("subid"), "submission")
        status.update(state="POLL", submission=submission)
        while True:
            submission_data = client.json(f"/api/submissions/{submission}")
            jobs = submission_data.get("jobs")
            finished = submission_data.get("processing_finished")
            if isinstance(jobs, list) and jobs and finished in (1, "1"):
                job = _id(jobs[0], "job")
                break
            sleep(min(0.75, client.remaining()))
        status.update(state="JOB", job=job)
        if client.json(f"/api/jobs/{job}").get("status") != "success":
            raise AnsvrError(f"ANSVR job {job} reported solve failure")
        status["state"] = "DOWNLOAD"
        data = client.request(f"/wcs_file/{job}")
        if not data.startswith(b"SIMPLE  =") or len(data) % 2880:
            raise AnsvrError("ANSVR did not return a complete FITS WCS")
        status["state"] = "WCS_RECEIVED"
        return data
    except (OSError, ValueError) as exc:
        status["error"] = str(exc)
        raise
    finally:
        status["duration_s"] = monotonic() - started
        write_json(transcript, status)
