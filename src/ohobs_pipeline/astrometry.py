"""Local Astrometry.net solving and held-out, epoch-aware catalogue validation."""

import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales

from . import ansvr_http, gaia, online_astrometry
from .config import Astrometry, astrometry_override
from .integrity import digest, identity, write_json
from .quality import Source


class AstrometryError(ValueError):
    """The configured astrometry stage could not establish a usable solution."""


@dataclass(frozen=True)
class Solution:
    wcs: WCS
    report: dict


def solver_files(settings: Astrometry) -> dict[str, Path | None]:
    """Locate the executables used by the selected local backend."""
    if settings.backend in ("ansvr_http", "local", "online", "auto"):
        return {}
    if settings.ansvr_root is not None:
        bin_dir = settings.ansvr_root / "bin"
        return {
            "executable": bin_dir / "solve-field",
            "solver_binary": settings.ansvr_root / "lib" / "astrometry" / "bin" / "solve-field.exe",
            "cygwin_bash": bin_dir / "bash.exe",
            "cygwin_cygpath": bin_dir / "cygpath.exe",
            "cygwin_runtime": bin_dir / "cygwin1.dll",
        }
    executable = shutil.which(settings.executable or "solve-field")
    return {"executable": Path(executable) if executable else None}


def external_inputs(settings: Astrometry) -> dict[str, str | None]:
    """Hash local files that influence a solve and its verification."""
    files = {
        **solver_files(settings),
        "catalogue": settings.catalogue,
        "backend_config": settings.backend_config,
        "index_manifest": settings.index_manifest,
    }
    return {
        name: digest(file) if file is not None and file.is_file() else None
        for name, file in files.items()
    }


def _cygwin_path(converter: Path, path: Path, timeout: int) -> str:
    try:
        result = subprocess.run(
            [str(converter), "-u", "--", str(path.resolve())],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AstrometryError(f"ANSVR Cygwin path conversion failed: {exc}") from exc
    converted = result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode or not converted.startswith("/") or "\n" in converted:
        raise AstrometryError(f"ANSVR Cygwin path conversion failed (exit {result.returncode})")
    return converted


def _solver_command(settings: Astrometry) -> list[str]:
    files = solver_files(settings)
    executable = files["executable"]
    if executable is None:
        raise AstrometryError("Astrometry.net solve-field executable unavailable")
    if settings.backend == "astrometry_net":
        return [str(executable)]
    if any(path is None or not path.is_file() for path in files.values()):
        raise AstrometryError("ANSVR bundled Cygwin or solve-field installation is incomplete")
    return [
        str(files["cygwin_bash"]),
        "--noprofile",
        "--norc",
        "-c",
        'export PATH=/usr/lib/astrometry/bin:/usr/bin:/bin; exec solve-field.exe "$@"',
        "osp-solve-field",
    ]


def probe_solver(settings: Astrometry) -> dict:
    """Check whether the local solver starts and responds to --help."""
    if settings.backend == "online":
        online_astrometry.Client(settings.online).login()
        return {"backend": "online", "status": "AVAILABLE", "url": settings.online.endpoint}
    if settings.backend in ("ansvr_http", "local", "auto"):
        local = settings.model_copy(update={"ansvr_url": settings.local_endpoint})
        ansvr_http.Client(local).login()
        return {
            "backend": "local" if settings.backend == "auto" else settings.backend,
            "status": "AVAILABLE",
            "url": settings.local_endpoint,
        }
    try:
        result = subprocess.run(
            [*_solver_command(settings), "--help"],
            capture_output=True,
            timeout=settings.timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AstrometryError(f"{settings.backend} launch failed: {exc}") from exc
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if result.returncode or not output.strip():
        raise AstrometryError(
            f"{settings.backend} help probe returned {result.returncode}: {output[-2000:]!r}"
        )
    return {
        "backend": settings.backend,
        "status": "AVAILABLE",
        "help_excerpt": output[:500],
        "external_inputs": external_inputs(settings),
    }


def load_candidate(header: fits.Header, shape: tuple[int, int], settings: Astrometry) -> WCS:
    """Require a finite celestial coordinate system with a valid pixel round trip."""
    if header.get("NAXIS") == 0:
        # Astrometry.net may return a header-only FITS solution.
        header = header.copy()
        del header["NAXIS"]
    wcs = WCS(header, fix=False)
    if wcs.pixel_n_dim != 2 or not wcs.has_celestial or wcs.world_n_dim != 2:
        raise AstrometryError("solver did not return a two-dimensional celestial WCS")
    h, w = shape
    px, py = np.meshgrid(np.linspace(0, w - 1, 7), np.linspace(0, h - 1, 7))
    sky = wcs.pixel_to_world(px, py)
    x, y = wcs.world_to_pixel(sky)
    scales = np.asarray(proj_plane_pixel_scales(wcs)) * 3600
    matrix = wcs.pixel_scale_matrix
    if (
        not np.isfinite(matrix).all()
        or abs(np.linalg.det(matrix)) < 1e-15
        or not np.isfinite(sky.icrs.ra.deg).all()
        or not np.isfinite(sky.icrs.dec.deg).all()
        or not np.allclose(x, px, atol=0.01, rtol=0)
        or not np.allclose(y, py, atol=0.01, rtol=0)
    ):
        raise AstrometryError("nonfinite or noninvertible celestial solution")
    if (
        settings.scale_min is not None
        and settings.scale_max is not None
        and (np.any(scales < settings.scale_min) or np.any(scales > settings.scale_max))
    ):
        raise AstrometryError("WCS pixel scale outside configured bounds")
    return wcs


def _catalogue(path: Path, time: Time) -> SkyCoord:
    table = Table.read(path, format="ascii.ecsv")
    columns = ("ra", "dec", "pmra", "pmdec", "ref_epoch")
    if any(name not in table.colnames for name in (*columns, "source_id")):
        raise AstrometryError(
            "reference catalogue requires Gaia source_id, ra, dec, pmra, pmdec, ref_epoch"
        )
    units = (u.deg, u.deg, u.mas / u.yr, u.mas / u.yr, u.yr)
    values = []
    for name, target in zip(columns, units, strict=True):
        col = table[name]
        unit = getattr(col, "unit", None)
        scale = 1 if unit is None else unit.to(target)
        values.append(np.ma.asarray(col, dtype=float).filled(np.nan) * scale)
    matrix = np.column_stack(values)
    keep = (
        np.isfinite(matrix).all(axis=1)
        & (np.abs(matrix[:, 1]) <= 90)
        & (matrix[:, 0] >= 0)
        & (matrix[:, 0] < 360)
    )
    if "ruwe" in table.colnames:
        keep &= np.ma.asarray(table["ruwe"], dtype=float).filled(np.inf) < 1.4
    if "duplicated_source" in table.colnames:
        keep &= ~np.ma.asarray(table["duplicated_source"], dtype=bool).filled(True)
    if not keep.any() or len(np.unique(table["source_id"][keep])) != keep.sum():
        raise AstrometryError("reference catalogue is empty or contains duplicate source IDs")
    ra, dec, pmra, pmdec, epoch = matrix[keep].T
    coords = SkyCoord(
        ra=ra * u.deg,
        dec=dec * u.deg,
        pm_ra_cosdec=pmra * u.mas / u.yr,
        pm_dec=pmdec * u.mas / u.yr,
        frame="icrs",
    )
    # Tangent-plane angular motion, first order. No assumed distances or RVs.
    displacement = np.hypot(pmra, pmdec) * (time.tcb.jyear - epoch) * u.mas
    pa = np.arctan2(pmra, pmdec) * u.rad
    return coords.directional_offset_by(pa, displacement)


def validate_catalogue(
    wcs: WCS,
    held: list[Source],
    catalogue: Path,
    time: Time,
    shape: tuple[int, int],
    settings: Astrometry,
) -> dict:
    """Measure independent mutual-nearest residuals before judging configured limits."""
    if len(held) < settings.min_matches:
        raise AstrometryError("insufficient held-out image candidates")
    px, py = np.array([(s.x, s.y) for s in held]).T
    sky = wcs.pixel_to_world(px, py).icrs
    gaia = _catalogue(catalogue, time)
    indices, distances, _ = sky.match_to_catalog_sky(gaia)
    reverse, _, _ = gaia.match_to_catalog_sky(sky)
    matched = (distances.arcsec <= settings.match_radius_arcsec) & (
        reverse[indices] == np.arange(len(held))
    )
    if not matched.any():
        raise AstrometryError("no unambiguous held-out catalogue matches")
    separation = distances.arcsec[matched]
    median = float(np.median(separation))
    scatter = float(1.4826 * np.median(np.abs(separation - median)))
    inlier = separation <= median + max(4 * scatter, 0.05)
    outliers = float(1 - np.mean(inlier))
    rms = float(np.sqrt(np.mean(separation[inlier] ** 2)))
    x, y = px[matched], py[matched]
    coverage = float(np.ptp(x[inlier]) * np.ptp(y[inlier]) / np.prod(shape))
    delta_ra, delta_dec = sky[matched].spherical_offsets_to(gaia[indices[matched]])
    sectors = []
    for right in (False, True):
        for top in (False, True):
            mask = inlier & ((x >= shape[1] / 2) == right) & ((y >= shape[0] / 2) == top)
            sectors.append(
                {
                    "x_half": "high" if right else "low",
                    "y_half": "high" if top else "low",
                    "inliers": int(mask.sum()),
                    "median_east_arcsec": float(np.median(delta_ra.arcsec[mask]))
                    if mask.any()
                    else None,
                    "median_north_arcsec": float(np.median(delta_dec.arcsec[mask]))
                    if mask.any()
                    else None,
                }
            )
    matrix = wcs.pixel_scale_matrix
    reasons = []
    if (
        inlier.sum() < settings.min_matches
        or inlier.sum() / len(held) < settings.min_match_fraction
        or coverage < settings.min_coverage_fraction
    ):
        reasons.append("insufficient held-out match count, completeness or field coverage")
    if outliers > settings.max_outlier_fraction:
        reasons.append("outlier fraction exceeds limit")
    if settings.max_rms_arcsec is None:
        reasons.append("verification RMS threshold is unspecified")
    elif rms > settings.max_rms_arcsec:
        reasons.append("RMS exceeds configured limit")
    if not settings.catalogue_independence_evidence:
        reasons.append("reference catalogue independence is undocumented")
    return {
        "schema_version": 1,
        "status": "VERIFIED" if not reasons else "UNVERIFIED",
        "reasons": reasons,
        "holdout_count": len(held),
        "match_count": int(matched.sum()),
        "inlier_count": int(inlier.sum()),
        "median_arcsec": median,
        "rms_arcsec": rms,
        "matched_rms_before_clipping_arcsec": float(np.sqrt(np.mean(separation**2))),
        "unmatched_count": int(len(held) - matched.sum()),
        "mad_arcsec": scatter,
        "outlier_fraction": outliers,
        "field_coverage_fraction": coverage,
        "scale_arcsec_px": (proj_plane_pixel_scales(wcs) * 3600).tolist(),
        "orientation_deg": math.degrees(math.atan2(matrix[0, 1], matrix[1, 1])),
        "parity": int(np.sign(np.linalg.det(matrix))),
        "sip_order": int(max(wcs.sip.a_order, wcs.sip.b_order)) if wcs.sip else None,
        "observation_epoch_tcb": float(time.tcb.jyear),
        "spatial_half_field_residuals": sectors,
        "residuals": [
            {
                "x": float(a),
                "y": float(b),
                "east_arcsec": float(c),
                "north_arcsec": float(d),
                "inlier": bool(e),
            }
            for a, b, c, d, e in zip(x, y, delta_ra.arcsec, delta_dec.arcsec, inlier, strict=True)
        ],
    }


def solve(
    sources: list[Source],
    shape: tuple[int, int],
    time: Time,
    settings: Astrometry,
    work: Path,
    pointing: tuple[float, float] | None = None,
    *,
    online_root: Path | None = None,
    image=None,
) -> Solution:
    """Solve a deterministic source subset and validate with untouched detections."""
    if settings.backend in ("online", "auto"):
        if settings.backend == "auto":
            try:
                return solve(
                    sources, shape, time, astrometry_override(settings, "local"), work, pointing
                )
            except (AstrometryError, OSError) as exc:
                if not settings.fallback_enabled:
                    raise
                work.mkdir(parents=True, exist_ok=True)
                write_json(work / "fallback.json", {"from": "local", "reason": str(exc)})
        return _solve_online(sources, shape, time, settings, work, pointing, online_root, image)
    http = settings.backend in ("ansvr_http", "local")
    if http:
        settings = settings.model_copy(update={"ansvr_url": settings.local_endpoint})
    prefix = [] if http else _solver_command(settings)
    held, fit = sources[::3], [s for i, s in enumerate(sources) if i % 3]
    if len(fit) < 6:
        raise AstrometryError("insufficient source candidates for plate solving")
    work.mkdir(parents=True, exist_ok=True)
    backend_config = str(settings.backend_config.resolve()) if settings.backend_config else None
    work_argument = str(work.resolve())
    if settings.backend == "ansvr":
        converter = solver_files(settings)["cygwin_cygpath"]
        assert converter is not None
        work_argument = _cygwin_path(converter, work, settings.timeout_s)
        if settings.backend_config is not None:
            backend_config = _cygwin_path(converter, settings.backend_config, settings.timeout_s)
    if settings.index_manifest is not None and not settings.index_manifest.is_file():
        raise AstrometryError("configured solver index manifest is unavailable")
    table = Table(
        {"X": [s.x + 1 for s in fit], "Y": [s.y + 1 for s in fit], "FLUX": [s.flux for s in fit]}
    )
    table_path = (work / "sources.xyls").resolve()
    table.write(table_path, format="fits")
    error = "solver did not produce WCS"
    for attempt in range(settings.attempts):
        started = monotonic()
        result = (work / f"solution-{attempt}.wcs").resolve()
        if http:
            try:
                result.write_bytes(
                    ansvr_http.solve_centroids(
                        settings,
                        fit,
                        shape,
                        pointing if attempt == 0 else None,
                        work / f"http-{attempt}.json",
                    )
                )
            except ansvr_http.AnsvrError as exc:
                error = str(exc)
                continue
        else:
            try:
                _run_native_attempt(
                    settings,
                    prefix,
                    work,
                    work_argument,
                    backend_config,
                    table_path,
                    result,
                    shape,
                    pointing,
                    attempt,
                )
            except AstrometryError as exc:
                error = str(exc)
                continue
        duration = monotonic() - started
        try:
            return assess_candidate(
                result,
                shape,
                held,
                time,
                settings,
                pointing,
                attempt=attempt + 1,
                solve_duration_s=duration,
                fitting_candidates=len(fit),
                source_digest=source_digest(sources),
                independent_holdout=True,
            )
        except (ValueError, OSError, RuntimeError, fits.VerifyError) as exc:
            error = f"invalid candidate WCS: {exc}"
    raise AstrometryError(error)


def assess_candidate(
    candidate: Path,
    shape: tuple[int, int],
    held: list[Source],
    time: Time,
    settings: Astrometry,
    pointing: tuple[float, float] | None = None,
    *,
    independent: bool = True,
    **metadata,
) -> Solution:
    """Apply one WCS geometry and Gaia acceptance policy to every candidate."""
    with fits.open(candidate, memmap=True, do_not_scale_image_data=True) as hdus:
        header = hdus["SCI"].header if "SCI" in hdus else hdus[0].header
    wcs = load_candidate(header, shape, settings)
    h, w = shape
    center = wcs.pixel_to_world((w - 1) / 2, (h - 1) / 2).icrs
    if pointing is not None and settings.pointing_radius_deg is not None:
        ra, dec = pointing
        if center.separation(SkyCoord(ra * u.deg, dec * u.deg)).deg > settings.pointing_radius_deg:
            raise AstrometryError("WCS center outside configured pointing bounds")
    report: dict = {
        "schema_version": 1,
        "status": "UNVERIFIED",
        "reasons": ["reference catalogue unavailable"],
    }
    if settings.catalogue is not None or settings.gaia.enabled:
        try:
            if settings.catalogue is not None:
                path = settings.catalogue
                reference = {"source": "local_ecsv", "sha256": digest(path)}
            else:
                cache = settings.gaia.cache_dir or candidate.parent / "gaia-cache"
                path, reference = gaia.reference(wcs, shape, time, settings.gaia, cache)
            report["reference_catalogue"] = reference
            report = {
                **validate_catalogue(wcs, held, path, time, shape, settings),
                "reference_catalogue": reference,
            }
        except (ValueError, KeyError, OSError, RuntimeError) as exc:
            report["reasons"] = [str(exc)]
    if not independent:
        report["status"] = "UNVERIFIED"
        report["reasons"].append("independent image-source holdout is not established")
    matrix = wcs.pixel_scale_matrix
    report.update(
        **metadata,
        backend=settings.backend,
        solve_status="SOLVED",
        holdout_count=len(held),
        center_ra_deg=float(center.ra.deg),
        center_dec_deg=float(center.dec.deg),
        scale_arcsec_px=(proj_plane_pixel_scales(wcs) * 3600).tolist(),
        orientation_deg=math.degrees(math.atan2(matrix[0, 1], matrix[1, 1])),
        parity=int(np.sign(np.linalg.det(matrix))),
    )
    return Solution(wcs, report)


def _solve_online(sources, shape, time, settings, work, pointing, root, image) -> Solution:
    work.mkdir(parents=True, exist_ok=True)
    root = root if root is not None else work / "astrometry-online"
    held, fit = sources[::3], [s for i, s in enumerate(sources) if i % 3]
    mode = settings.online.upload_mode
    actual = "image" if mode == "image" else "source_list"
    try:
        data, receipt = online_astrometry.solve(settings, root, fit, shape, pointing, image, actual)
    except online_astrometry.NovaError as exc:
        if mode != "image_fallback" or exc.category not in {
            "INSUFFICIENT_SOURCES",
            "SOLVER_FAILED",
        }:
            raise
        actual = "image"
        data, receipt = online_astrometry.solve(settings, root, fit, shape, pointing, image, actual)
    candidate = work / "nova.wcs"
    candidate.write_bytes(data)
    write_json(work / "nova-receipt.json", receipt)
    verification = settings.model_copy(
        update={
            "backend": "online",
            "catalogue_independence_evidence": settings.online.catalogue_independence_evidence,
        }
    )
    try:
        return assess_candidate(
            candidate,
            shape,
            held,
            time,
            verification,
            pointing,
            independent=actual == "source_list" and not receipt.get("manually_attached"),
            receipt_id=receipt["id"],
            submission_id=receipt["submission_id"],
            job_id=receipt["job_id"],
            solve_duration_s=receipt["elapsed_s"],
            fitting_candidates=receipt["fit_count"],
            upload_mode=actual,
            solver_calibration=receipt["calibration"],
            source_digest=source_digest(sources),
            candidate_sha256=digest(candidate),
            independent_holdout=actual == "source_list" and not receipt.get("manually_attached"),
        )
    except (ValueError, OSError, RuntimeError, fits.VerifyError):
        raise online_astrometry.NovaError(
            "INVALID_WCS", "Nova WCS did not pass geometric validation"
        ) from None


def source_digest(sources: list[Source]) -> str:
    return identity([(float(s.x), float(s.y), float(s.flux)) for s in sources])


def _run_native_attempt(
    settings: Astrometry,
    prefix: list[str],
    work: Path,
    work_argument: str,
    backend_config: str | None,
    table_path: Path,
    result: Path,
    shape: tuple[int, int],
    pointing: tuple[float, float] | None,
    attempt: int,
) -> None:
    h, w = shape
    cmd = [
        *prefix,
        "--no-plots",
        "--overwrite",
        "--no-verify",
        "--dir",
        work_argument,
        "--out",
        f"solve-{attempt}",
        "--wcs",
        f"{work_argument}/solution-{attempt}.wcs" if settings.backend == "ansvr" else str(result),
        "--width",
        str(w),
        "--height",
        str(h),
        "--x-column",
        "X",
        "--y-column",
        "Y",
        "--sort-column",
        "FLUX",
        "--cpulimit",
        str(settings.timeout_s),
    ]
    if backend_config is not None:
        cmd += ["--backend-config", backend_config]
    if settings.scale_min is not None and settings.scale_max is not None:
        cmd += [
            "-u",
            "arcsecperpix",
            "-L",
            str(settings.scale_min),
            "-H",
            str(settings.scale_max),
        ]
    if pointing is not None and settings.pointing_radius_deg is not None and attempt == 0:
        ra, dec = pointing
        cmd += [
            "--ra",
            str(ra),
            "--dec",
            str(dec),
            "--radius",
            str(settings.pointing_radius_deg),
        ]
    with (work / f"solver-{attempt}.log").open("wb") as log:
        try:
            execution = subprocess.run(
                [
                    *cmd,
                    f"{work_argument}/sources.xyls"
                    if settings.backend == "ansvr"
                    else str(table_path),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=settings.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise AstrometryError(f"solver timed out after {settings.timeout_s} seconds") from None
    if execution.returncode != 0 or not result.is_file():
        raise AstrometryError(
            f"{settings.backend} returned {execution.returncode} without usable WCS"
            f" on attempt {attempt + 1}; inspect solver log"
        )
