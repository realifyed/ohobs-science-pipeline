"""Mask-aware source candidate detection and local elliptical Gaussian PSF fitting."""

import math
from dataclasses import asdict, dataclass

import numpy as np
from astropy.stats import sigma_clipped_stats
from scipy.ndimage import gaussian_filter, maximum_filter, uniform_filter, zoom
from scipy.optimize import least_squares

from .config import Quality
from .dq import DQ
from .reduction import Calibrated

FWHM_FACTOR = 2 * math.sqrt(2 * math.log(2))


@dataclass(frozen=True)
class Source:
    x: float
    y: float
    flux: float
    fwhm: float
    ellipticity: float
    snr: float | None
    angle_deg: float


def _background(science, valid, box: int):
    h, w = science.shape
    ny, nx = max(1, h // box), max(1, w // box)
    level, rms = np.full((ny, nx), np.nan), np.full((ny, nx), np.nan)
    ys, xs = np.linspace(0, h, ny + 1, dtype=int), np.linspace(0, w, nx + 1, dtype=int)
    for j in range(ny):
        for i in range(nx):
            tile = np.s_[ys[j] : ys[j + 1], xs[i] : xs[i + 1]]
            if np.count_nonzero(valid[tile]) >= max(16, valid[tile].size // 4):
                _, level[j, i], rms[j, i] = sigma_clipped_stats(science[tile][valid[tile]])
    if not np.isfinite(level).any() or not np.any(rms > 0):
        raise ValueError("insufficient unmasked pixels with measurable background scatter")
    grid = np.where(np.isfinite(level), level, np.nanmedian(level))
    noise = np.where(rms > 0, rms, np.nanmedian(rms[rms > 0]))
    return (
        zoom(grid, (h / ny, w / nx), order=1, grid_mode=True, mode="nearest"),
        zoom(noise, (h / ny, w / nx), order=1, grid_mode=True, mode="nearest"),
        level,
        rms,
    )


def _fit(residual, variance, x: int, y: int, radius: int) -> Source | None:
    tile = np.s_[y - radius : y + radius + 1, x - radius : x + radius + 1]
    data = residual[tile]
    yy, xx = np.mgrid[-radius : radius + 1, -radius : radius + 1]
    var = variance[tile]
    weights_known = bool(np.all(np.isfinite(var) & (var > 0)))
    weight = 1 / np.sqrt(var) if weights_known else 1.0

    def difference(p):
        amplitude, cx, cy, sx, sy, a, sky = p
        dx, dy = xx - cx, yy - cy
        u = np.cos(a) * dx + np.sin(a) * dy
        v = -np.sin(a) * dx + np.cos(a) * dy
        return (
            (sky + amplitude * np.exp(-0.5 * ((u / sx) ** 2 + (v / sy) ** 2)) - data) * weight
        ).ravel()

    fit = least_squares(
        difference,
        [data[radius, radius], 0, 0, 1.5, 1.5, 0, 0],
        bounds=(
            [0, -2, -2, 0.45, 0.45, -np.pi, -np.inf],
            [np.inf, 2, 2, radius / 2, radius / 2, np.pi, np.inf],
        ),
        max_nfev=120,
    )
    if not fit.success or np.any(fit.active_mask) or not np.all(np.isfinite(fit.x)):
        return None
    amplitude, cx, cy, sx, sy, angle, _ = fit.x
    # Discourage fitting single-pixel peaks or unresolved structures.
    fwhm = float(FWHM_FACTOR * np.sqrt(sx * sy))
    if min(sx, sy) * FWHM_FACTOR < 1.5:
        return None
    angle += np.pi / 2 if sy > sx else 0
    flux = float(2 * np.pi * amplitude * sx * sy)
    snr = None
    if weights_known and np.linalg.matrix_rank(fit.jac) == 7:
        grad = np.array([flux / amplitude, 0, 0, flux / sx, flux / sy, 0, 0])
        covariance = np.linalg.pinv(fit.jac.T @ fit.jac)
        error_sq = float(grad @ covariance @ grad)
        if error_sq > 0:
            snr = flux / np.sqrt(error_sq)
    return Source(
        float(x + cx),
        float(y + cy),
        flux,
        fwhm,
        float(1 - min(sx, sy) / max(sx, sy)),
        snr,
        float(np.degrees(angle) % 180),
    )


def measure(image: Calibrated, settings: Quality, saturation_known: bool = False):
    """Return a versioned report and isolated PSF candidates in zero-based pixels."""
    data = image.science
    valid = np.isfinite(data) & (image.dq == 0)
    background, rms, grid, tile_rms = _background(data, valid, settings.box)
    residual = np.where(valid, data - background, -np.inf)
    r = settings.fit_radius
    safe = ~maximum_filter(~valid, size=2 * r + 1, mode="nearest")
    safe[:r] = safe[-r:] = False
    safe[:, :r] = safe[:, -r:] = False
    detection = residual
    if (sigma := settings.detection_smoothing_sigma_px) is not None:
        # Smooth the detection image only. Normalize across masked pixels and
        # keep the threshold in original-background RMS units.
        support = gaussian_filter(valid.astype(float), sigma, mode="nearest")
        detection = gaussian_filter(np.where(valid, residual, 0), sigma, mode="nearest")
        np.divide(detection, support, out=detection, where=support > 0)
        detection[~valid] = -np.inf
    maxima = (detection > settings.threshold_sigma * rms) & (
        detection == maximum_filter(detection, size=3, mode="nearest")
    )
    y, x = np.nonzero(maxima & safe & (residual > 0))
    # Reject blended windows rather than reporting single-source morphologies.
    blended = uniform_filter(maxima.astype(float), size=2 * r + 1, mode="constant")
    order = np.argsort(-detection[y, x], kind="stable")[: settings.max_sources]
    sources: list[Source] = []
    for i in order:
        j, k = int(y[i]), int(x[i])
        if blended[j, k] < 1.5 / (2 * r + 1) ** 2:
            result = _fit(residual, image.variance, k, j, r)
            if result is not None:
                sources.append(result)
    fwhms = [s.fwhm for s in sources]
    ell = [s.ellipticity for s in sources]
    snrs = [s.snr for s in sources if s.snr is not None]
    median_fwhm = float(np.median(fwhms)) if fwhms else None
    median_ell = float(np.median(ell)) if ell else None
    reasons = []
    limits = [
        (len(sources), settings.min_sources, "source count below minimum", False),
        (median_fwhm, settings.max_fwhm_px, "FWHM above maximum", True),
        (median_ell, settings.max_ellipticity, "ellipticity above maximum", True),
    ]
    unavailable = []
    for value, limit, reason, upper in limits:
        if limit is not None:
            if value is None:
                unavailable.append(reason)
            elif (value > limit) if upper else (value < limit):
                reasons.append(reason)
    status = (
        "FAIL"
        if reasons
        else "NOT_EVALUATED"
        if unavailable
        else "PASS"
        if any(limit is not None for _, limit, _, _ in limits)
        else "NOT_EVALUATED"
    )
    if (
        status in ("PASS", "NOT_EVALUATED")
        and median_fwhm is not None
        and settings.warn_fwhm_px is not None
        and median_fwhm > settings.warn_fwhm_px
    ):
        status = "WARN"
        reasons.append("FWHM above configured advisory limit")
    elongated = [s for s in sources if s.ellipticity >= 0.15]
    axial = (
        np.mean(np.exp(2j * np.radians([s.angle_deg for s in elongated]))) if elongated else None
    )
    # Fit a plane to coarse background levels. Extended emission can drive this metric.
    gy, gx = np.indices(grid.shape, dtype=float)
    finite = np.isfinite(grid)
    gradient = None
    if grid.shape[0] > 1 and grid.shape[1] > 1 and np.count_nonzero(finite) >= 3:
        design = np.column_stack(
            (
                np.ones(finite.sum()),
                gx[finite] * data.shape[1] / grid.shape[1],
                gy[finite] * data.shape[0] / grid.shape[0],
            )
        )
        if np.linalg.matrix_rank(design) == 3:
            gradient = np.linalg.lstsq(design, grid[finite], rcond=None)[0][1:].tolist()
    psf_cells = []
    for iy in range(2):
        for ix in range(2):
            cell = [
                s
                for s in sources
                if int(s.x >= data.shape[1] / 2) == ix and int(s.y >= data.shape[0] / 2) == iy
            ]
            psf_cells.append(
                {
                    "column": ix,
                    "row": iy,
                    "count": len(cell),
                    "fwhm_px": float(np.median([s.fwhm for s in cell])) if cell else None,
                    "ellipticity": float(np.median([s.ellipticity for s in cell]))
                    if cell
                    else None,
                }
            )
    return {
        "schema_version": 1,
        "profile": settings.profile,
        "status": status,
        "reasons": reasons + [f"metric unavailable: {r}" for r in unavailable],
        "source_count": len(sources),
        "psf_quadrants": psf_cells,
        "detected_peaks": int(maxima.sum()),
        "candidate_density_per_megapixel": len(sources) * 1e6 / data.size,
        "fwhm_px": median_fwhm,
        "fwhm_mad_px": float(np.median(np.abs(np.array(fwhms) - median_fwhm)))
        if median_fwhm is not None
        else None,
        "ellipticity": median_ell,
        "tracking_indicator": {
            "population": len(elongated),
            "axial_coherence": float(abs(axial)) if axial is not None else None,
            "axis_deg": float(np.degrees(np.angle(axial)) / 2 % 180) if axial is not None else None,
            "interpretation": "Elongation can also reflect optics or the atmosphere.",
        },
        "median_psf_sharpness_px_inv": float(1 / median_fwhm) if median_fwhm else None,
        "median_model_snr": float(np.median(snrs)) if snrs else None,
        "background": float(np.nanmedian(grid)),
        "background_rms": float(np.nanmedian(tile_rms)),
        "bad_pixel_fraction": float(
            np.count_nonzero(image.dq & int(DQ.BAD_PIXEL | DQ.HOT_PIXEL | DQ.DEAD_PIXEL))
            / data.size
        ),
        "background_gradient_per_px": gradient,
        "background_grid": [[float(v) if np.isfinite(v) else None for v in row] for row in grid],
        "flagged_fraction": float(np.count_nonzero(image.dq) / data.size),
        "saturated_fraction": float(np.count_nonzero(image.dq & int(DQ.SATURATED)) / data.size)
        if saturation_known
        else None,
        "dq_fractions": {
            flag.name: float(np.count_nonzero(image.dq & int(flag)) / data.size)
            for flag in DQ
            if flag != DQ.SATURATED or saturation_known
        },
        "sources": [asdict(s) for s in sources],
        "interpretation": "Background can include extended emission. Fitted objects are candidates.",
    }, sources
