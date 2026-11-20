"""Read-only, strict FITS ingestion and explicit metadata normalization."""

from __future__ import annotations

import math
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from astropy.io import fits
from astropy.time import Time, TimeDelta
from astropy.utils.exceptions import AstropyUserWarning
from astropy.wcs import WCS
from numpy.typing import NDArray

from .config import Config
from .integrity import digest
from .origin import FitsError, Origin, classify_origin, require_workflow

Kind = Literal["BIAS", "DARK", "FLAT", "FLAT_DARK", "LIGHT"]
FIELDS = {
    "camera": ("CAMERAID", "INSTRUME"),
    "model": ("INSTRUME",),
    "readout": ("READOUTM", "READMODE"),
    "gain": ("GAIN",),
    "offset": ("OFFSET",),
    "bin_x": ("XBINNING", "CCDXBIN"),
    "bin_y": ("YBINNING", "CCDYBIN"),
    "roi_x": ("XORGSUBF",),
    "roi_y": ("YORGSUBF",),
    "temp": ("CCD-TEMP", "SENSORT"),
    "exposure": ("EXPTIME", "EXPOSURE"),
    "filter": ("FILTER",),
    "optics": ("OPTICID",),
    "unit": ("BUNIT",),
    "kind": ("IMAGETYP", "OBSTYPE"),
}
REQUIRED_SETTINGS = (
    "camera",
    "model",
    "readout",
    "gain",
    "offset",
    "bin_x",
    "bin_y",
    "roi_x",
    "roi_y",
    "unit",
)
NUMERIC = {"gain", "offset", "temp", "exposure", "bin_x", "bin_y", "roi_x", "roi_y"}
KINDS = {
    "LIGHT": "LIGHT",
    "OBJECT": "LIGHT",
    "SCIENCE": "LIGHT",
    "DARK": "DARK",
    "FLAT": "FLAT",
    "FLAT_DARK": "FLAT_DARK",
    "DARK_FLAT": "FLAT_DARK",
    "DARKFLAT": "FLAT_DARK",
    "FLATDARK": "FLAT_DARK",
    "BIAS": "BIAS",
    "ZERO": "BIAS",
}


@dataclass(frozen=True)
class Frame:
    path: Path
    sha256: str
    signature: tuple[int, int, int, int, int]
    shape: tuple[int, int]
    extension: int
    values: dict
    sources: dict
    header: fits.Header
    start: str | None
    midpoint: str | None
    end: str | None
    time_scale: str | None
    wcs_status: str
    time_deltas_ms: dict[str, float]
    origin: Origin = "observational"

    def manifest(self) -> dict:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "data_origin": self.origin,
            "shape": self.shape,
            "hdu": self.extension,
            "metadata": self.values,
            "metadata_sources": self.sources,
            "start": self.start,
            "midpoint": self.midpoint,
            "end": self.end,
            "time_scale": self.time_scale,
            "raw_wcs": self.wcs_status,
            "date_minus_mjd_ms": self.time_deltas_ms,
            "original_header": self.header.tostring(sep="\n", padding=False),
        }

    @contextmanager
    def image(self) -> Iterator[Image]:
        with open_fits(self.path) as hdus:
            if file_signature(self.path) != self.signature:
                raise FitsError(f"input changed: {self.path}")
            yield Image(hdus[self.extension])
        if file_signature(self.path) != self.signature:
            raise FitsError(f"input changed while reading: {self.path}")


class Image:
    def __init__(self, hdu):
        self.hdu = hdu
        self.scale = float(hdu.header.get("BSCALE", 1))
        self.zero = float(hdu.header.get("BZERO", 0))
        self.blank = hdu.header.get("BLANK")
        if not math.isfinite(self.scale) or not math.isfinite(self.zero) or self.scale == 0:
            raise FitsError("invalid FITS scaling")
        if self.blank is not None:
            bitpix = hdu.header["BITPIX"]
            if bitpix < 0 or not isinstance(self.blank, int):
                raise FitsError("BLANK is an integer-storage sentinel")
            lo, hi = (0, 255) if bitpix == 8 else (-(2 ** (bitpix - 1)), 2 ** (bitpix - 1) - 1)
            if not lo <= self.blank <= hi:
                raise FitsError("BLANK outside stored integer range")

    def rows(self, start: int, stop: int) -> NDArray[np.float64]:
        raw = self.hdu.section[start:stop, :]
        # Float64 exactly represents the supported raw integer range (up to 32 bits).
        data = raw.astype(np.float64)
        if self.blank is not None:
            data[raw == self.blank] = np.nan
        with np.errstate(over="ignore", invalid="ignore"):
            data *= self.scale
            data += self.zero
        return data


def open_fits(path: Path):
    return fits.open(
        path,
        mode="denywrite",
        memmap=True,
        do_not_scale_image_data=True,
        uint=False,
        lazy_load_hdus=False,
    )


def file_signature(path: Path) -> tuple[int, int, int, int, int]:
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _normalized(header: fits.Header, config: Config | None, shape: tuple[int, int]):
    values: dict[str, Any] = {}
    sources: dict[str, Any] = {}
    for key, aliases in FIELDS.items():
        source = next((name for name in aliases if name in header and header[name] != ""), None)
        observed = {name: header[name] for name in aliases if name in header}
        overridden = config is not None and key in config.overrides
        value = (
            config.overrides[key]
            if overridden and config is not None
            else header.get(source)
            if source
            else None
        )
        if key == "exposure" and len(observed) > 1 and not overridden:
            exposures = [float(v) for v in observed.values()]
            if any(not math.isclose(v, exposures[0], rel_tol=0, abs_tol=1e-9) for v in exposures):
                raise FitsError("EXPTIME and EXPOSURE disagree")
        if value is not None and key in NUMERIC:
            value = float(value)
            if not math.isfinite(value):
                raise FitsError(f"non-finite {key}")
            if key in ("bin_x", "bin_y", "roi_x", "roi_y"):
                if not value.is_integer() or value < (1 if key.startswith("bin") else 0):
                    raise FitsError(f"invalid {key}")
                value = int(value)
        if isinstance(value, str):
            value = value.strip() or None
        values[key] = value
        sources[key] = {"selected": "operator" if overridden else source, "observed": observed}
    if values["kind"] is not None:
        kind = str(values["kind"]).upper().replace("-", "_").replace(" ", "_")
        if kind not in KINDS:
            raise FitsError(f"unrecognized frame type: {kind}")
        values["kind"] = KINDS[kind]
    if values["unit"] is not None:
        values["unit"] = {
            "adu": "adu",
            "electron": "electron",
            "electrons": "electron",
            "e-": "electron",
        }.get(str(values["unit"]).lower(), values["unit"])
    exposure = values["exposure"]
    if exposure is not None and (exposure < 0 or (exposure == 0 and values["kind"] != "BIAS")):
        raise FitsError("invalid exposure duration")
    if config is not None:
        detector = config.detector
        for field in ("model", "readout"):
            expected = getattr(detector, field)
            if expected is not None and values[field] != expected:
                raise FitsError(f"unexpected {field}: {values[field]!r}; configured {expected!r}")
        if detector.full_shape == shape and (values["bin_x"], values["bin_y"]) == (1, 1):
            for key in ("roi_x", "roi_y"):
                if values[key] is None:
                    values[key] = 0
                    sources[key]["selected"] = "full-frame geometry inference"
    return values, sources


def _time(header: fits.Header, exposure: float | None):
    dates = ("DATE-OBS", "DATE-AVG", "DATE-END")
    if not any(k in header for k in (*dates, "DATE-UTC", "MJD-OBS", "MJD-AVG", "MJD-END")):
        return None, None, None, None, {}
    scale = str(header.get("TIMESYS", "UTC")).lower()
    if scale not in ("utc", "tai", "tt", "tdb", "ut1", "tcb", "tcg"):
        raise FitsError(f"unsupported TIMESYS: {scale}")
    parsed: list[Time | None] = []
    differences: dict[str, float] = {}
    for key in dates:
        mjd = key.replace("DATE", "MJD")
        if key == "DATE-OBS" and key not in header and scale == "utc" and "DATE-UTC" in header:
            key = "DATE-UTC"
        value = (
            Time(header[key], scale=scale)
            if key in header
            else (Time(header[mjd], format="mjd", scale=scale) if mjd in header else None)
        )
        if value is not None and key in header and mjd in header:
            delta = (value - Time(header[mjd], format="mjd", scale=scale)).sec * 1000
            differences[key] = float(delta)
            if abs(delta) > 2:
                raise FitsError(f"{key} and {mjd} disagree by more than 2 ms")
        parsed.append(value)
    start, midpoint, end = parsed
    if start is not None and exposure is not None:
        midpoint = (
            midpoint if midpoint is not None else start + TimeDelta(exposure / 2, format="sec")
        )
        end = end if end is not None else start + TimeDelta(exposure, format="sec")
    if (
        (start is not None and midpoint is not None and midpoint < start)
        or (end is not None and midpoint is not None and end < midpoint)
        or (start is not None and end is not None and end < start)
    ):
        raise FitsError("invalid exposure timestamp ordering")
    return (
        *(x.isot if x is not None else None for x in (start, midpoint, end)),
        scale,
        differences,
    )


def inspect_frame(path: Path, config: Config | None = None) -> Frame:
    """Verify HDU layout, integrity and metadata without loading the image."""
    path = path.resolve(strict=True)
    if not path.is_file():
        raise FitsError(f"not a regular file: {path}")
    before = file_signature(path)
    if config is not None and before[2] > config.max_input_mib * 2**20:
        raise FitsError("FITS input exceeds the configured file-size limit")
    if before[2] == 0 or before[2] % 2880:
        raise FitsError("FITS size is not a positive multiple of 2880 bytes")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", fits.verify.VerifyWarning)
            warnings.filterwarnings(
                "error", message="File may have been truncated", category=AstropyUserWarning
            )
            with open_fits(path) as hdus:
                hdus.verify("exception")
                for hdu in hdus:
                    if hdu._data_offset + hdu._data_size > before[2]:
                        raise FitsError("truncated FITS data")
                    if "CHECKSUM" in hdu.header and hdu.verify_checksum() != 1:
                        raise FitsError("FITS CHECKSUM mismatch")
                    if "DATASUM" in hdu.header and hdu.verify_datasum() != 1:
                        raise FitsError("FITS DATASUM mismatch")
                indices = [
                    i
                    for i, h in enumerate(hdus)
                    if type(h) in (fits.PrimaryHDU, fits.ImageHDU) and h.header.get("NAXIS") == 2
                ]
                if len(indices) != 1:
                    raise FitsError("expected exactly one uncompressed two-dimensional image HDU")
                index = indices[0]
                hdu = hdus[index]
                if hdu.header["BITPIX"] not in (8, 16, 32, -32, -64):
                    raise FitsError("unsupported BITPIX")
                Image(hdu)
                shape = (hdu.header["NAXIS2"], hdu.header["NAXIS1"])
                if min(shape) < 1:
                    raise FitsError("empty image")
                header = hdu.header.copy()
                if index:
                    for card in hdus[0].header.cards:
                        if (
                            card.keyword not in header
                            and card.keyword
                            not in {"SIMPLE", "BITPIX", "NAXIS", "EXTEND", "CHECKSUM", "DATASUM"}
                            and not card.keyword.startswith("NAXIS")
                        ):
                            header.append(card)
                origin = classify_origin(*(h.header for h in hdus))
                values, sources = _normalized(header, config, shape)
                if header.get("BAYERPAT"):
                    raise FitsError("CFA input is outside OSP's monochrome calibration scope")
                start, mid, end, scale, differences = _time(header, values["exposure"])
                wcs = "ABSENT"
                if any(k in header for k in ("CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2")):
                    try:
                        wcs = "UNVERIFIED" if WCS(header, fix=False).has_celestial else "INVALID"
                    except (ValueError, RuntimeError):
                        wcs = "INVALID"
        checksum = digest(path)
    except FitsError:
        raise
    except (fits.VerifyError, Warning, TypeError, ValueError, OverflowError) as exc:
        raise FitsError(f"{path}: {exc}") from exc
    if file_signature(path) != before:
        raise FitsError(f"input changed while inspecting: {path}")
    return Frame(
        path,
        checksum,
        before,
        shape,
        index,
        values,
        sources,
        header,
        start,
        mid,
        end,
        scale,
        wcs,
        differences,
        origin,
    )


def require_calibration_metadata(frame: Frame, config: Config) -> None:
    require_workflow(frame.origin, config.synthetic_test)
    needed: tuple[str, ...] = (*REQUIRED_SETTINGS, "kind", "exposure", "temp")
    if frame.values["kind"] in ("LIGHT", "FLAT"):
        needed = (*needed, "filter", "optics")
    missing = [key for key in needed if frame.values[key] is None]
    missing += [key for key in config.calibration.detector_keys if key not in frame.header]
    if frame.values["kind"] in ("LIGHT", "FLAT"):
        missing += [key for key in config.calibration.optical_keys if key not in frame.header]
    if missing:
        raise FitsError(f"{frame.path}: missing calibration metadata: {', '.join(missing)}")
    if frame.values["unit"] not in ("adu", "electron"):
        raise FitsError("calibration requires explicit ADU or electron units")
    if frame.values["kind"] == "LIGHT" and frame.start is None:
        raise FitsError("science exposure requires observation start time")
