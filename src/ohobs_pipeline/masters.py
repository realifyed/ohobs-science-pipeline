"""Content-addressed master calibration products and physical compatibility."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from astropy.io import fits

from .combination import combine
from .config import Config
from .dq import DQ, FATAL, raw_mask
from .ingest import (
    REQUIRED_SETTINGS,
    Frame,
    Image,
    inspect_frame,
    open_fits,
    require_calibration_metadata,
)
from .integrity import (
    digest,
    identity,
    object_id,
    publish_directory,
    read_json,
    versions,
    write_json,
)
from .origin import Origin, classify_origin, stamp_origin


class CalibrationError(ValueError):
    """Calibration inputs are absent, ambiguous, invalid or incompatible."""


def detector_key(frame: Frame, config: Config) -> dict:
    return {
        **{k: frame.values[k] for k in REQUIRED_SETTINGS},
        **({"synthetic": True} if frame.origin != "observational" else {}),
        "shape": list(frame.shape),
        "headers": {k: frame.header[k] for k in config.calibration.detector_keys},
    }


def optical_key(frame: Frame, config: Config) -> dict:
    return {
        "filter": frame.values["filter"],
        "optics": frame.values["optics"],
        "headers": {k: frame.header[k] for k in config.calibration.optical_keys},
    }


@dataclass(frozen=True)
class Master:
    directory: Path
    manifest: dict

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @contextmanager
    def images(self) -> Iterator[dict[str, Image]]:
        path = self.directory / "master.fits"
        if digest(path) != self.manifest["sha256"]:
            raise CalibrationError(f"master checksum mismatch: {self.id}")
        with open_fits(path) as hdus:
            if classify_origin(hdus[0].header) != master_origin(self):
                raise CalibrationError("master FITS origin differs from its manifest")
            yield {h.name: Image(h) for h in hdus[1:]}


def master_origin(master: Master) -> Origin:
    definition = master.manifest["definition"]
    recorded = definition.get("data_origin")
    synthetic = definition["detector"].get("synthetic") is True
    if recorded == "observational" and not synthetic:
        return "observational"
    if isinstance(recorded, list) and len(recorded) == 2 and synthetic:
        return recorded[0], recorded[1]
    if recorded is None and not synthetic:
        # Older masters carry original FITS headers even though origin was not explicit.
        frames = master.manifest.get("frames", [])
        if (
            [row.get("sha256") for row in frames] == definition["inputs"]
            and frames
            and all(
                classify_origin(fits.Header.fromstring(row["original_header"], sep="\n"))
                == "observational"
                for row in frames
            )
        ):
            return "observational"
    raise CalibrationError("master origin is unverified; rebuild it from acceptable raw inputs")


def load_master(config: Config, identifier: str) -> Master:
    folder = config.work_dir / "masters" / object_id(identifier)
    manifest = read_json(folder / "manifest.json")
    if (
        manifest["id"] != identifier
        or identity(manifest["definition"]) != identifier
        or manifest["schema_version"] != 1
    ):
        raise CalibrationError(f"invalid master manifest: {identifier}")
    return Master(folder, manifest)


def list_masters(config: Config) -> Iterator[Master]:
    for folder in sorted((config.work_dir / "masters").glob("*")):
        if folder.is_dir() and not folder.name.startswith("."):
            yield load_master(config, folder.name)


def compatible(master: Master, frame: Frame, config: Config, kind: str) -> bool:
    definition = master.manifest["definition"]
    if definition["kind"] != kind or definition["detector"] != detector_key(frame, config):
        return False
    if (
        master_origin(master) != frame.origin
        or (frame.origin != "observational") != config.synthetic_test
    ):
        return False
    if kind == "FLAT":
        return definition["optics"] == optical_key(frame, config)
    if kind == "BIAS":
        return (
            bias_eligible(frame.values["exposure"], config)
            and definition["exposure"] == 0
            and all(
                abs(t - frame.values["temp"]) <= config.calibration.temperature_tolerance_c + 1e-12
                for t in definition["temperature_range"]
            )
        )
    if kind not in ("DARK", "FLAT_DARK"):
        raise CalibrationError(f"no selection rule for {kind}")
    return definition["exposure"] == frame.values["exposure"] and all(
        abs(t - frame.values["temp"]) <= config.calibration.temperature_tolerance_c + 1e-12
        for t in definition["temperature_range"]
    )


def bias_eligible(exposure: float, config: Config) -> bool:
    limit = config.calibration.bias_only_max_exposure_s
    return limit is not None and exposure <= limit


def reference_kind(config: Config) -> str:
    """Select the explicitly configured electronic-offset correction method."""
    return "BIAS" if config.calibration.bias_only_max_exposure_s is not None else "DARK"


def verify_flat_lineage(flat: Master, config: Config) -> Master:
    """Recheck transitive flat-dark matching under the current processing policy."""
    definition = flat.manifest["definition"]
    identifier = definition.get("flat_dark")
    if not identifier:
        raise CalibrationError("flat has no matched flat-dark lineage")
    dependency = load_master(config, identifier)
    dark = dependency.manifest["definition"]
    limit = config.calibration.temperature_tolerance_c
    role = "BIAS" if reference_kind(config) == "BIAS" else "FLAT_DARK"
    reference_matches = (
        dark["exposure"] == 0 and bias_eligible(definition["exposure"], config)
        if role == "BIAS"
        else dark["exposure"] == definition["exposure"]
    )
    if (
        dark["kind"] != role
        or dark["detector"] != definition["detector"]
        or master_origin(dependency) != master_origin(flat)
        or not reference_matches
        or dependency.manifest["sha256"] != definition["flat_dark_sha256"]
        or any(
            abs(a - b) > limit + 1e-12
            for a in dark["temperature_range"]
            for b in definition["temperature_range"]
        )
    ):
        raise CalibrationError("flat-dark lineage violates current matching policy")
    return dependency


def select_master(
    frame: Frame,
    config: Config,
    kind: str,
    identifier: str | None = None,
    registry: tuple[Master, ...] | None = None,
) -> Master:
    require_calibration_metadata(frame, config)
    available = (
        [load_master(config, identifier)]
        if identifier
        else registry
        if registry is not None
        else list_masters(config)
    )
    matches = [m for m in available if compatible(m, frame, config, kind)]
    if len(matches) != 1:
        raise CalibrationError(
            f"{frame.path.name}: expected one compatible {kind}, found "
            f"{len(matches)} ({', '.join(m.id for m in matches)})"
        )
    return matches[0]


def _master_files(temp: Path, shape: tuple[int, int]):
    specifications = {
        "DATA": "float64",
        "VAR": "float64",
        "TEMPVAR": "float64",
        "DQ": "uint16",
        "COUNT": "int32",
        "REJECT": "int32",
    }
    return {
        k: np.memmap(temp / (k + ".array"), dtype=d, mode="w+", shape=shape)
        for k, d in specifications.items()
    }


def _populate(arrays, frames: list[Frame], config: Config, flat_dark: Master | None):
    shape = frames[0].shape
    # Bound row stacks, including conservative headroom for bootstrap and clipping.
    bytes_per_row = shape[1] * (len(frames) * 80 + 160)
    rows = min(shape[0], config.memory_mib * 2**20 // bytes_per_row)
    if not rows:
        raise CalibrationError("master memory budget is smaller than one working row")
    is_flat = flat_dark is not None
    minima = np.full(len(frames), np.inf)
    maxima = np.full(len(frames), -np.inf)
    valid_counts = np.zeros(len(frames), dtype=np.int64)
    peak_counts = np.zeros(len(frames), dtype=np.int64)
    peak_limit = config.calibration.flat_peak_code_fraction_max
    with ExitStack() as stack:
        images = [stack.enter_context(f.image()) for f in frames]
        dark = stack.enter_context(flat_dark.images()) if flat_dark else None
        for first in range(0, shape[0], rows):
            last = min(first + rows, shape[0])
            data = np.empty((len(frames), last - first, shape[1]))
            for i, (image, frame) in enumerate(zip(images, frames, strict=True)):
                tile = image.rows(first, last)
                tile[raw_mask(tile, frame, config, first) & FATAL != 0] = np.nan
                data[i] = tile
                if is_flat:
                    finite = tile[np.isfinite(tile)]
                    if finite.size:
                        minima[i] = min(minima[i], float(finite.min()))
                        tile_max = float(finite.max())
                        if peak_limit is not None:
                            valid_counts[i] += finite.size
                            if tile_max > maxima[i]:
                                peak_counts[i] = 0
                            if tile_max >= maxima[i]:
                                peak_counts[i] += np.count_nonzero(finite == tile_max)
                        maxima[i] = max(maxima[i], tile_max)
            mean, variance, temporal, count, reject = combine(data, config.calibration)
            mask = np.zeros(mean.shape, dtype=np.uint16)
            mask[~np.isfinite(mean)] |= int(DQ.CALIBRATION_SUSPECT)
            if dark:
                # Translation-invariant estimators: subtract one common flat-dark
                # after combination and propagate its uncertainty exactly once.
                mean -= dark["DATA"].rows(first, last)
                variance += dark["VAR"].rows(first, last)
                mask |= dark["DQ"].rows(first, last).astype(np.uint16)
            arrays["DATA"][first:last] = mean
            arrays["VAR"][first:last] = variance
            arrays["TEMPVAR"][first:last] = temporal
            arrays["DQ"][first:last] = mask
            arrays["COUNT"][first:last] = count
            arrays["REJECT"][first:last] = reject
    if is_flat and np.any(minima >= maxima):
        invalid = [frames[i].path.name for i in np.flatnonzero(minima >= maxima)]
        raise CalibrationError("flat has constant or wholly masked samples: " + ", ".join(invalid))
    if is_flat and peak_limit is not None:
        crowded_peaks = np.flatnonzero(peak_counts > peak_limit * valid_counts)
        if crowded_peaks.size:
            names = ", ".join(
                f"{frames[i].path.name} ({peak_counts[i] / valid_counts[i]:.2%})"
                for i in crowded_peaks
            )
            raise CalibrationError("flat peak-code occupancy exceeds configured limit: " + names)


def _write_master(path: Path, arrays, definition: dict):
    primary = fits.PrimaryHDU()
    primary.header["OSPSCHM"] = 1
    primary.header["DQVER"] = 1
    primary.header["CALTYPE"] = definition["kind"]
    stamp_origin(primary.header, definition["data_origin"])
    unit = definition["detector"]["unit"]
    units = {
        "DATA": "1" if definition["kind"] == "FLAT" else unit,
        "VAR": "1" if definition["kind"] == "FLAT" else unit + "2",
        "TEMPVAR": unit + "2",
    }
    extensions = []
    for name, data in arrays.items():
        hdu = fits.ImageHDU(data=data, name=name)
        if name in units:
            hdu.header["BUNIT"] = units[name]
        extensions.append(hdu)
    fits.HDUList([primary, *extensions]).writeto(path, checksum=True)


def build_master(
    paths: list[Path], config: Config, *, flat_dark_id: str | None = None, kind: str | None = None
) -> Master:
    """Build a homogeneous master. Role override can explicitly identify dark flats."""
    frames = sorted((inspect_frame(path, config) for path in paths), key=lambda f: f.sha256)
    if len(frames) < config.calibration.min_frames:
        raise CalibrationError("insufficient calibration frames")
    for frame in frames:
        require_calibration_metadata(frame, config)
    if len({f.sha256 for f in frames}) != len(frames):
        raise CalibrationError("duplicate source checksums in master")
    first = frames[0]
    observed = first.values["kind"]
    role = kind or observed
    if observed not in ("BIAS", "DARK", "FLAT_DARK", "FLAT"):
        raise CalibrationError("master requires calibration inputs")
    if role != observed and (role, observed) != ("FLAT_DARK", "DARK"):
        raise CalibrationError("only a DARK can be explicitly assigned the FLAT_DARK role")
    detector = detector_key(first, config)
    optics = optical_key(first, config) if role == "FLAT" else None
    exposure = first.values["exposure"]
    temps = [f.values["temp"] for f in frames]
    if max(temps) - min(temps) > config.calibration.temperature_tolerance_c + 1e-12:
        raise CalibrationError("input temperatures exceed configured maximum spread")
    if any(
        f.values["kind"] != observed
        or f.origin != first.origin
        or detector_key(f, config) != detector
        or f.values["exposure"] != exposure
        or (optics is not None and optical_key(f, config) != optics)
        for f in frames
    ):
        raise CalibrationError("input calibration frames are heterogeneous")
    if flat_dark_id and role != "FLAT":
        raise CalibrationError("flat-dark input is only used when building a flat")
    correction = "BIAS" if reference_kind(config) == "BIAS" else "FLAT_DARK"
    dark = select_master(first, config, correction, flat_dark_id) if role == "FLAT" else None
    if dark and any(not compatible(dark, f, config, correction) for f in frames):
        raise CalibrationError("flat-dark does not match every flat exposure")
    if dark and {f.sha256 for f in frames}.intersection(dark.manifest["definition"]["inputs"]):
        raise CalibrationError("flat and flat-dark input samples overlap")
    payload = {
        "kind": role,
        "data_origin": first.origin,
        "detector": detector,
        "optics": optics,
        "exposure": exposure,
        "temperature_range": [min(temps), max(temps)],
        "inputs": [f.sha256 for f in frames],
        "flat_dark": dark.id if dark else None,
        "flat_dark_sha256": dark.manifest["sha256"] if dark else None,
        "estimator": config.calibration.model_dump(mode="json"),
        "profile": config.detector.model_dump(mode="json"),
        "overrides": config.overrides,
        "version": versions(),
    }
    identifier = identity(payload)
    target = config.work_dir / "masters" / identifier
    if target.exists():
        existing = load_master(config, identifier)
        with existing.images():
            return existing
    # The normalization median uses one full-frame scratch selection and vectorized
    # FITS finalization may materialize another plane.
    if np.prod(first.shape) * 48 > config.memory_mib * 2**20:
        raise CalibrationError("master finalization exceeds configured memory budget")
    with publish_directory(target) as temp:
        arrays = _master_files(temp, first.shape)
        _populate(arrays, frames, config, dark)
        normalization = None
        if role == "FLAT":
            data = arrays["DATA"]
            valid = np.isfinite(data) & (arrays["DQ"] == 0)
            if not np.any(valid):
                raise CalibrationError("flat has no valid normalization pixels")
            normalization = float(np.median(data[valid]))
            if not np.isfinite(normalization) or normalization <= 0:
                raise CalibrationError("flat median must be positive and finite")
            data /= normalization
            arrays["VAR"] /= normalization**2
            invalid = ~valid | ~np.isfinite(data) | (data < config.calibration.flat_min_response)
            arrays["DQ"][invalid] |= int(DQ.FLAT_INVALID)
            data[invalid] = np.nan
            arrays["VAR"][invalid] = np.nan
            del data
        valid_pixels = int(np.count_nonzero(arrays["DQ"] == 0))
        if not valid_pixels:
            raise CalibrationError("master has no usable pixels")
        statistics = {
            "valid_pixels": valid_pixels,
            "pixels": int(np.prod(first.shape)),
            "rejected_samples": int(arrays["REJECT"].sum()),
            "min_contributing_samples": int(arrays["COUNT"].min()),
            "max_contributing_samples": int(arrays["COUNT"].max()),
        }
        _write_master(temp / "master.fits", arrays, payload)
        for name in arrays:
            arrays[name].flush()
        arrays.clear()
        for path in temp.glob("*.array"):
            path.unlink()
        write_json(
            temp / "manifest.json",
            {
                "schema_version": 1,
                "id": identifier,
                "definition": payload,
                "created_utc": datetime.now(UTC).isoformat(),
                "sha256": digest(temp / "master.fits"),
                "normalization": normalization,
                "statistics": statistics,
                "frames": [f.manifest() for f in frames],
            },
        )
    return load_master(config, identifier)
