"""Nova HTTPS transport, upload policy and persistent, resumable job receipts."""

import http.client
import io
import json
import math
import os
import socket
import ssl
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic, sleep, time
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from .config import Astrometry, Online
from .integrity import identity, object_id, read_json
from .job_lock import job_lock
from .quality import Source

KEY_ENV = "OSP_ASTROMETRY_API_KEY"
ACTIVE = {"RESERVED", "SUBMITTING", "PENDING", "UPLOAD_UNKNOWN"}


class NovaError(ValueError):
    """A redacted failure with a stable category for CLI and batch reports."""

    def __init__(self, category: str, detail: str, *, pending: bool = False):
        super().__init__(detail)
        self.category = category
        self.pending = pending


class HttpFailure(NovaError):
    def __init__(self, status: int, retry_after: float):
        super().__init__("HTTP", f"Nova returned HTTP {status}")
        self.status = status
        self.retry_after = retry_after


class Client:
    def __init__(self, settings: Online, *, cancel_file: Path | None = None):
        self.settings = settings
        self.deadline = monotonic() + settings.timeout_s
        self.cancel_file = cancel_file

    def remaining(self) -> float:
        if self.cancel_file is not None and self.cancel_file.exists():
            raise NovaError(
                "CANCELLED", "Local wait cancelled. Nova may still process the submission."
            )
        left = self.deadline - monotonic()
        if left <= 0:
            raise NovaError(
                "TIMEOUT", "Local solve deadline expired. Check the saved receipt to resume."
            )
        return left

    def pause(self, seconds: float) -> None:
        until = monotonic() + seconds
        while (left := until - monotonic()) > 0:
            sleep(min(left, self.remaining(), 0.25))

    def request(
        self,
        path: str,
        body: bytes | None = None,
        mime: str | None = None,
        *,
        upload: bool = False,
    ) -> bytes:
        for retry in range(self.settings.retries + 1):
            retry_after = 0.0
            try:
                return self._request_once(path, body, mime)
            except HttpFailure as exc:
                retry_after = exc.retry_after
                transient = exc.status == 429 or (
                    not upload and exc.status in {408, 500, 502, 503, 504}
                )
                if not transient or retry == self.settings.retries:
                    raise
            except NovaError as exc:
                if (
                    upload
                    or exc.category not in {"NETWORK", "DNS"}
                    or retry == self.settings.retries
                ):
                    raise
            self.pause(max(retry_after, min(15, 2**retry)))
        raise AssertionError("unreachable retry loop")

    def _request_once(self, path: str, body: bytes | None, mime: str | None) -> bytes:
        endpoint = urlsplit(self.settings.endpoint)
        connection = http.client.HTTPSConnection(
            endpoint.hostname or "nova.astrometry.net",
            timeout=min(self.settings.request_timeout_s, self.remaining()),
            context=ssl.create_default_context(),
        )
        headers = {"Connection": "close", "User-Agent": "OHOBS-Science-Pipeline"}
        if mime:
            headers["Content-Type"] = mime
        try:
            connection.request("POST" if body is not None else "GET", path, body, headers)
            with connection.getresponse() as response:
                if response.status != 200:
                    after = (response.getheader("Retry-After") or "").strip()
                    delay = _retry_after(after)
                    raise HttpFailure(response.status, delay)
                data = response.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    raise NovaError("PROTOCOL", "Nova response exceeds the allowed size")
                # Commit an upload acknowledgement as soon as it is parsed.
                if body is None:
                    self.remaining()
                return data
        except ssl.SSLError:
            raise NovaError(
                "TLS", "Nova TLS negotiation or certificate verification failed"
            ) from None
        except socket.gaierror:
            raise NovaError("DNS", "Could not resolve nova.astrometry.net") from None
        except (OSError, http.client.HTTPException):
            raise NovaError("NETWORK", "Nova HTTPS connection or response failed") from None
        finally:
            connection.close()

    def json(
        self, path: str, body: bytes | None = None, mime: str | None = None, *, upload: bool = False
    ) -> dict:
        try:
            reply = json.loads(self.request(path, body, mime, upload=upload))
        except (UnicodeError, ValueError) as exc:
            if isinstance(exc, NovaError):
                raise
            raise NovaError("PROTOCOL", "Nova returned malformed JSON") from None
        if not isinstance(reply, dict):
            raise NovaError("PROTOCOL", "Nova JSON response is not an object")
        return reply

    def login(self) -> str:
        key = os.environ.get(KEY_ENV, "").strip()
        if not key:
            raise NovaError("MISSING_CREDENTIAL", f"Set {KEY_ENV} in the process environment")
        try:
            reply = self.json("/api/login", _form({"apikey": key}), _FORM)
        except HttpFailure as exc:
            if exc.status in (401, 403):
                raise NovaError("AUTHENTICATION", "Nova authentication was rejected") from None
            raise
        token = reply.get("session")
        if (
            reply.get("status") != "success"
            or not isinstance(token, str)
            or not token
            or len(token) > 256
        ):
            raise NovaError("AUTHENTICATION", "Nova authentication was rejected")
        return token

    def submit(self, fields: dict, image: bytes | None, token: str) -> str:
        for renewal in range(2):
            params = {**fields, "session": token}
            try:
                if image is None:
                    reply = self.json("/api/url_upload", _form(params), _FORM, upload=True)
                else:
                    body, mime = _multipart(params, image)
                    reply = self.json("/api/upload", body, mime, upload=True)
            except HttpFailure as exc:
                if exc.status != 401:
                    raise
                reply = {"status": "error", "errormessage": "invalid session"}
            if reply.get("status") == "success":
                return _remote_id(reply.get("subid"))
            message = str(reply.get("errormessage", "")).lower()
            if "session" in message and ("invalid" in message or "expired" in message):
                if renewal == 0:
                    token = self.login()
                    continue
                raise NovaError("AUTHENTICATION", "Nova rejected the renewed session")
            raise NovaError("REJECTED", "Nova rejected the submission")
        raise AssertionError("unreachable authentication renewal")


_FORM = "application/x-www-form-urlencoded"


def _retry_after(value: str) -> float:
    if value.isascii() and value.isdecimal() and len(value) < 8:
        return float(min(3600, int(value)))
    try:
        return min(3600.0, max(0.0, parsedate_to_datetime(value).timestamp() - time()))
    except (TypeError, ValueError, OverflowError, OSError):
        return 0.0


def _form(fields: dict) -> bytes:
    return urlencode({"request-json": json.dumps(fields, allow_nan=False)}).encode("ascii")


def _multipart(fields: dict, image: bytes) -> tuple[bytes, str]:
    boundary = uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="request-json"\r\n'
        f"Content-Type: text/plain\r\n\r\n{json.dumps(fields, allow_nan=False)}\r\n"
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="image.fits"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("ascii")
    return head + image + f"\r\n--{boundary}--\r\n".encode(
        "ascii"
    ), f"multipart/form-data; boundary={boundary}"


def _remote_id(value: object) -> str:
    val = str(value)
    if not (1 <= len(val) <= 20 and val.isascii() and val.isdecimal() and int(val) > 0):
        raise NovaError("PROTOCOL", "Nova returned an invalid job or submission identifier")
    return val


def positions(
    points: list[Source], shape: tuple[int, int], maximum: int
) -> list[tuple[float, float]]:
    h, w = shape
    valid = [
        s
        for s in points
        if 0 <= s.x <= w - 1 and 0 <= s.y <= h - 1 and math.isfinite(s.flux) and s.flux > 0
    ]
    ordered = sorted(valid, key=lambda s: (-s.flux, s.x, s.y))
    return list(dict.fromkeys((float(s.x + 1), float(s.y + 1)) for s in ordered))[:maximum]


def _image_bytes(image, shape: tuple[int, int], limit_mib: int) -> bytes:
    if image is None or image.shape != shape:
        raise NovaError("IMAGE_REQUIRED", "Image upload requires a matching single image plane")
    limit = limit_mib * 2**20
    if image.size * 4 + 5760 > limit:
        raise NovaError("IMAGE_SIZE", "Image exceeds the configured upload limit")
    with io.BytesIO() as buffer:
        fits.PrimaryHDU(np.asarray(image, dtype=np.float32)).writeto(buffer)
        return buffer.getvalue()


def _atomic(path: Path, data: bytes) -> None:
    with NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _save(path: Path, state: dict) -> None:
    _atomic(path, (json.dumps(state, allow_nan=False, indent=2) + "\n").encode())


@contextmanager
def _lock(path: Path, client: Client) -> Iterator[None]:
    # Retry the lock entrance only. A ValueError inside the critical section
    # must propagate without replaying an upload.
    while True:
        client.remaining()
        guard = job_lock(path)
        try:
            guard.__enter__()
        except ValueError:
            client.pause(0.2)
            continue
        break
    try:
        yield
    finally:
        guard.__exit__(None, None, None)


def _poll(client: Client, submission: str) -> str:
    delay = client.settings.poll_s
    while True:
        data = client.json(f"/api/submissions/{submission}")
        jobs = data.get("jobs") or []
        if not isinstance(jobs, list):
            raise NovaError("PROTOCOL", "Nova returned an invalid jobs list")
        states = []
        for value in jobs:
            if value is None:
                continue
            job = _remote_id(value)
            status = client.json(f"/api/jobs/{job}").get("status")
            if status == "success":
                return job
            states.append(status)
        if (
            jobs
            and None not in jobs
            and states
            and all(status in ("failure", "failed") for status in states)
            and data.get("processing_finished")
        ):
            raise NovaError("SOLVER_FAILED", "Nova reported a terminal solve failure")
        client.pause(delay)
        delay = min(max(15, client.settings.poll_s), delay * 1.5)


def _finish(client: Client, path: Path, record: dict) -> bytes:
    wcs_path = path.with_suffix(".wcs")
    if record["state"] == "SOLVED":
        data = wcs_path.read_bytes()
        if sha256(data).hexdigest() != record["wcs_sha256"]:
            raise NovaError("INTEGRITY", "Cached Nova WCS differs from its receipt")
        return data
    try:
        job = _poll(client, _remote_id(record["submission_id"]))
        raw_cal = client.json(f"/api/jobs/{job}/calibration/")
        cal = {
            k: float(v)
            for k in ("ra", "dec", "pixscale", "orientation", "radius", "parity")
            if isinstance((v := raw_cal.get(k)), (int, float)) and abs(v) <= 1e20
        }
        data = _clean_wcs(client.request(f"/wcs_file/{job}"))
        _atomic(wcs_path, data)
        record.update(
            state="SOLVED",
            job_id=job,
            calibration=cal,
            wcs_sha256=sha256(data).hexdigest(),
            elapsed_s=max(0, time() - record["started_at"]),
        )
        record.pop("last_wait", None)
    except NovaError as exc:
        record["last_wait"] = exc.category
        if exc.category in {"SOLVER_FAILED", "INVALID_WCS"}:
            record["state"] = "FAILED"
        raise
    finally:
        _save(path, record)
    return data


def _clean_wcs(data: bytes) -> bytes:
    """Store celestial transform cards only; discard returned metadata or HDUs."""
    if not data.startswith(b"SIMPLE  =") or len(data) % 2880:
        raise NovaError("INVALID_WCS", "Nova did not return a complete FITS WCS")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            source = fits.getheader(io.BytesIO(data))
            if source.get("NAXIS") == 0:
                del source["NAXIS"]
            wcs = WCS(source, fix=False)
            if not wcs.has_celestial or wcs.pixel_n_dim != 2 or wcs.world_n_dim != 2:
                raise ValueError("not a 2D celestial WCS")
            header = wcs.to_header(relax=True)
            for key in ("WCSNAME", "CNAME1", "CNAME2"):
                if key in header:
                    del header[key]
        with io.BytesIO() as sink:
            fits.PrimaryHDU(header=header).writeto(sink, checksum=True)
            return sink.getvalue()
    except (ValueError, OSError, RuntimeError, fits.VerifyError):
        raise NovaError("INVALID_WCS", "Nova returned an unreadable celestial WCS") from None


def _reserve(client: Client, path: Path, record: dict) -> None:
    while True:
        with _lock(path.parent / "admission.lock", client):
            active = 0
            for item in path.parent.glob("*.json"):
                try:
                    active += read_json(item).get("state") in ACTIVE
                except FileNotFoundError:
                    continue
            if active < client.settings.max_concurrent_jobs:
                _save(path, record)
                return
        client.pause(client.settings.poll_s)


def solve(
    settings: Astrometry,
    root: Path,
    points: list[Source],
    shape: tuple[int, int],
    pointing: tuple[float, float] | None,
    image,
    mode: str,
) -> tuple[bytes, dict]:
    """Submit once per payload; preserve unresolved and ambiguous submissions."""
    policy = settings.online
    if not policy.authorize_upload:
        raise NovaError(
            "AUTHORIZATION_REQUIRED",
            "Nova submission requires explicit online upload authorization",
        )
    if mode == "image" and not policy.authorize_image_upload:
        raise NovaError(
            "AUTHORIZATION_REQUIRED",
            "Nova image submission requires separate image upload authorization",
        )
    h, w = shape
    fields: dict = {
        "image_width": w,
        "image_height": h,
        "allow_commercial_use": "n",
        "allow_modifications": "n",
        "publicly_visible": "y" if policy.publicly_visible else "n",
    }
    if settings.scale_min is not None:
        fields.update(
            scale_units="arcsecperpix",
            scale_type="ul",
            scale_lower=settings.scale_min,
            scale_upper=settings.scale_max,
        )
    if (
        pointing
        and settings.pointing_radius_deg
        and all(math.isfinite(v) for v in pointing)
        and -90 <= pointing[1] <= 90
    ):
        fields.update(
            center_ra=pointing[0] % 360, center_dec=pointing[1], radius=settings.pointing_radius_deg
        )
    payload = None
    fit = positions(points, shape, policy.max_sources) if mode == "source_list" else []
    if mode == "source_list":
        if len(fit) < 6 or np.linalg.matrix_rank(np.asarray(fit) - np.mean(fit, axis=0)) < 2:
            raise NovaError(
                "INSUFFICIENT_SOURCES",
                "Nova needs at least six distinct, non-collinear fitting sources",
            )
        fields.update(x=[p[0] for p in fit], y=[p[1] for p in fit])
    else:
        payload = _image_bytes(image, shape, policy.max_image_mib)
    key = identity(
        {
            "endpoint": policy.endpoint,
            "request": fields,
            "image_sha256": sha256(payload).hexdigest() if payload is not None else None,
        }
    )
    root.mkdir(parents=True, exist_ok=True)
    path = root / (key + ".json")
    client = Client(policy, cancel_file=path.with_suffix(".cancel"))
    with _lock(path.with_suffix(".lock"), client):
        if path.exists():
            record = read_json(path)
            if record["state"] in {"SUBMITTING", "UPLOAD_UNKNOWN"}:
                raise NovaError(
                    "UPLOAD_UNKNOWN",
                    f"Prior upload may have been accepted. Inspect receipt {key}",
                    pending=True,
                )
            if record["state"] == "FAILED":
                raise NovaError(
                    record.get("last_wait", "SOLVER_FAILED"),
                    f"Prior Nova solve did not yield a usable WCS. Receipt {key}",
                )
            if record["state"] == "ABANDONED":
                raise NovaError("ABANDONED", f"The ambiguous upload was retired. Receipt {key}")
        else:
            if not os.environ.get(KEY_ENV, "").strip():
                raise NovaError("MISSING_CREDENTIAL", f"Set {KEY_ENV} in the process environment")
            record = {
                "schema_version": 1,
                "id": key,
                "endpoint": policy.endpoint,
                "state": "RESERVED",
                "upload_mode": mode,
                "shape": list(shape),
                "fit_digest": identity(fit),
                "fit_count": len(fit),
                "started_at": time(),
            }
            _reserve(client, path, record)
        if record["state"] == "RESERVED":
            try:
                token = client.login()
            except NovaError:
                path.unlink(missing_ok=True)
                raise
            record["state"] = "SUBMITTING"
            _save(path, record)
            try:
                record.update(state="PENDING", submission_id=client.submit(fields, payload, token))
            except NovaError as exc:
                clear = exc.category in {"AUTHENTICATION", "MISSING_CREDENTIAL", "REJECTED"} or (
                    isinstance(exc, HttpFailure) and 400 <= exc.status < 500 and exc.status != 408
                )
                if clear:
                    path.unlink(missing_ok=True)
                else:
                    record["state"] = "UPLOAD_UNKNOWN"
                    _save(path, record)
                raise NovaError(
                    exc.category,
                    f"{exc}. Receipt {key}" if not clear else str(exc),
                    pending=not clear,
                ) from None
            _save(path, record)
        try:
            return _finish(client, path, record), record
        except NovaError as exc:
            raise NovaError(
                exc.category, f"{exc} Receipt {key}", pending=record["state"] == "PENDING"
            ) from None


def status(
    settings: Online,
    root: Path,
    identifier: str,
    *,
    wait: bool = False,
    cancel: bool = False,
    submission_id: str | None = None,
    abandon: bool = False,
) -> dict:
    """Inspect remote job status or manage an OSP receipt without uploading."""
    if len(identifier) != 64:
        if wait or cancel or submission_id is not None or abandon:
            raise ValueError("receipt actions require an OSP receipt ID")
        job = _remote_id(identifier)
        reported = Client(settings).json(f"/api/jobs/{job}").get("status")
        return {
            "job_id": job,
            "status": reported if reported in ("success", "failure", "solving") else "unknown",
        }
    path = root / (object_id(identifier) + ".json")
    record = read_json(path)
    flag = path.with_suffix(".cancel")
    if cancel and record["state"] in ACTIVE:
        flag.touch()
    if wait or submission_id is not None or abandon:
        flag.unlink(missing_ok=True)
        client = Client(settings, cancel_file=flag)
        with _lock(path.with_suffix(".lock"), client):
            record = read_json(path)
            if abandon:
                if record["state"] not in {"RESERVED", "SUBMITTING", "UPLOAD_UNKNOWN"}:
                    raise ValueError("only an ambiguous upload receipt can be retired")
                record["state"] = "ABANDONED"
                _save(path, record)
            if submission_id is not None:
                if record["state"] not in {"SUBMITTING", "UPLOAD_UNKNOWN"}:
                    raise ValueError("attach a reference only to an ambiguous upload receipt")
                record.update(
                    state="PENDING", submission_id=_remote_id(submission_id), manually_attached=True
                )
                _save(path, record)
            if wait and record["state"] in {"PENDING", "SOLVED"}:
                try:
                    _finish(client, path, record)
                except NovaError as exc:
                    raise NovaError(
                        exc.category,
                        f"{exc} Receipt {identifier}",
                        pending=record["state"] == "PENDING",
                    ) from None
    result = {**record, "local_wait_cancelled": flag.exists()}
    if record["state"] == "SOLVED":
        result["wcs_path"] = str(path.with_suffix(".wcs"))
    return result
