"""Science FITS layout, verification, and independently usable pixel arrays."""

from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from .config import Config
from .dq import DQ, FATAL
from .ingest import Frame
from .integrity import digest, identity, read_json
from .origin import classify_origin, stamp_origin
from .reduction import Calibrated


def write_science(
    path: Path,
    image: Calibrated,
    frame: Frame,
    config: Config,
    definition: dict,
    state: str,
    qc: dict,
    astrometry: dict,
    wcs=None,
) -> None:
    primary = fits.PrimaryHDU()
    header = primary.header
    header["OSPSCHM"] = 1
    header["DQVER"] = 1
    header["OSPSTATE"] = state
    header["OSPVER"] = definition["software"]["osp"]
    header["OBS_ID"] = frame.sha256
    header["OBSERVAT"] = config.node
    stamp_origin(header, frame.origin)
    header["DARKID"] = definition["masters"]["dark"]["id"]
    header["FLATID"] = definition["masters"]["flat"]["id"]
    header["CONFHASH"] = definition["config_hash"]
    header["EXPTIME"] = frame.values["exposure"]
    header["DATE-OBS"] = frame.start
    header["DATE-AVG"] = frame.midpoint
    header["DATE-END"] = frame.end
    header["TIMESYS"] = frame.time_scale.upper() if frame.time_scale else "UTC"
    header["ERRSTAT"] = image.noise_status
    from .dq import characterized

    header["SATKNOWN"] = characterized(frame, config) and config.detector.saturation is not None
    header["QCSTAT"] = qc["status"]
    header["WCSSTAT"] = astrometry["status"]
    for key in ("OBJECT", "TELESCOP", "SITELAT", "SITELONG", "SITEELEV", "ROWORDER"):
        if key in frame.header:
            header[key] = frame.header[key]
    for key, field in {
        "INSTRUME": "model",
        "CAMERAID": "camera",
        "FILTER": "filter",
        "OPTICID": "optics",
        "READOUTM": "readout",
        "GAIN": "gain",
        "OFFSET": "offset",
        "CCD-TEMP": "temp",
        "XBINNING": "bin_x",
        "YBINNING": "bin_y",
    }.items():
        header[key] = frame.values[field]
    if definition["masters"]["dark"].get("kind") == "BIAS":
        header["BIASONLY"] = True
        header.add_history(
            "Independent bias and normalized flat applied under negligible-dark policy."
        )
    else:
        header.add_history("Matched dark (includes offset) and normalized flat applied.")
    sci = fits.ImageHDU(image.science, name="SCI")
    err = fits.ImageHDU(np.sqrt(image.variance), name="ERR")
    dq = fits.ImageHDU(image.dq, name="DQ")
    sci.header["BUNIT"] = err.header["BUNIT"] = frame.values["unit"]
    if wcs is not None:
        sci.header.update(wcs.to_header(relax=True))
    for bit in DQ:
        dq.header[f"DQBIT{bit.value.bit_length() - 1}"] = bit.name
    fits.HDUList([primary, sci, err, dq]).writeto(path, checksum=True)


def _verify_hdus(hdus) -> None:
    hdus.verify("exception")
    if [h.name for h in hdus] != ["PRIMARY", "SCI", "ERR", "DQ"]:
        raise ValueError("unexpected science product HDUs")
    primary, science, error, dq = hdus
    if primary.header.get("OSPSCHM") != 1 or primary.header.get("DQVER") != 1:
        raise ValueError("unsupported science product schema")
    for hdu in hdus:
        if hdu.verify_checksum() != 1 or hdu.verify_datasum() != 1:
            raise ValueError(f"checksum missing or invalid in {hdu.name}")
    if not (science.shape == error.shape == dq.shape and len(science.shape) == 2):
        raise ValueError("incompatible science product shapes")
    if science.header.get("BUNIT") not in ("adu", "electron") or (
        science.header["BUNIT"] != error.header.get("BUNIT")
    ):
        raise ValueError("invalid science and error units")
    if (
        science.header["BITPIX"] not in (-32, -64)
        or error.header["BITPIX"] not in (-32, -64)
        or dq.header["BITPIX"] != 16
        or dq.header.get("BZERO") != 32768
    ):
        raise ValueError("unsupported science array storage")
    wcs_status = primary.header.get("WCSSTAT")
    if wcs_status not in ("VERIFIED", "UNVERIFIED", "FAILED", "NOT_EVALUATED"):
        raise ValueError("invalid WCS status")
    has_wcs = WCS(science.header, fix=False).has_celestial
    if has_wcs != (wcs_status == "VERIFIED"):
        raise ValueError("WCSSTAT does not agree with the published celestial WCS")
    status = primary.header.get("ERRSTAT")
    if status not in ("UNAVAILABLE", "PARTIAL", "CONDITIONAL"):
        raise ValueError("invalid uncertainty status")
    allowed = sum(int(flag) for flag in DQ)
    with_error = without_error = 0
    for row in range(0, science.shape[0], 128):
        cut = np.s_[row : row + 128, :]
        e, s, flags = error.section[cut], science.section[cut], dq.section[cut]
        if np.any(
            np.isinf(s)
            | np.isinf(e)
            | (e <= 0)
            | (~np.isfinite(s) & (flags & FATAL == 0))
            | (np.isfinite(s) & (flags & FATAL != 0))
            | (~np.isfinite(s) & np.isfinite(e))
        ):
            raise ValueError("invalid pixel or uncertainty semantics")
        if np.any(flags & np.uint16(65535 ^ allowed)):
            raise ValueError("unknown DQ flags")
        with_error += int(np.count_nonzero(np.isfinite(e)))
        without_error += int(np.count_nonzero(np.isfinite(s) & ~np.isfinite(e)))
    expected = "UNAVAILABLE" if with_error == 0 else "PARTIAL" if without_error else "CONDITIONAL"
    if status != expected:
        raise ValueError("ERRSTAT does not match uncertainty coverage")
    if primary.header.get("OSPSTATE") == "COMPLETE" and (
        status != "CONDITIONAL" or primary.header.get("WCSSTAT") != "VERIFIED"
    ):
        raise ValueError("COMPLETE requires verified WCS and full uncertainty coverage")


def validate_product(path: Path, *, provenance: bool = True) -> dict:
    """Verify FITS integrity, pixel semantics and, when requested, sidecar integrity."""
    with fits.open(path, memmap=False) as hdus:
        _verify_hdus(hdus)
        header = hdus[0].header
        result = {
            "state": header["OSPSTATE"],
            "wcs": header["WCSSTAT"],
            "noise": header["ERRSTAT"],
            "shape": hdus["SCI"].shape,
        }
        keys = ("OBS_ID", "DARKID", "FLATID", "CONFHASH", "OSPVER")
        fits_ids = {k: header.get(k) for k in keys}
        origin_headers = [hdu.header for hdu in hdus]
    if provenance:
        manifest = read_json(path.parent / "provenance.json")
        if manifest["schema_version"] != 1 or manifest["id"] != identity(manifest["definition"]):
            raise ValueError("invalid provenance identity")
        definition = manifest["definition"]
        if "data_origin" in definition:
            origin = classify_origin(*origin_headers)
            if definition["data_origin"] != (list(origin) if isinstance(origin, tuple) else origin):
                raise ValueError("science FITS origin disagrees with provenance")
        expected_ids = dict(
            zip(
                keys,
                (
                    definition["input_sha256"],
                    definition["masters"]["dark"]["id"],
                    definition["masters"]["flat"]["id"],
                    definition["config_hash"],
                    definition["software"]["osp"],
                ),
                strict=True,
            )
        )
        if fits_ids != expected_ids or identity(manifest["config"]) != definition["config_hash"]:
            raise ValueError("FITS identities or configuration disagree with provenance")
        if manifest["state"] != result["state"] or manifest["outputs"].get(path.name) != digest(
            path
        ):
            raise ValueError("science FITS differs from provenance")
        for name, expected in manifest["outputs"].items():
            relative = Path(name)
            artifact = path.parent / relative
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not artifact.resolve().is_relative_to(path.parent.resolve())
                or digest(artifact) != expected
            ):
                raise ValueError(f"output checksum mismatch: {name}")
    return result


def read_calibrated(path: Path) -> Calibrated:
    validate_product(path, provenance=False)
    with fits.open(path, memmap=False) as hdus:
        return Calibrated(
            hdus["SCI"].data.astype(np.float64),
            hdus["ERR"].data.astype(np.float64) ** 2,
            hdus["DQ"].data.astype(np.uint16),
            hdus[0].header["ERRSTAT"],
        )
