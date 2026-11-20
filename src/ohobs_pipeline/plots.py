"""Measured diagnostic plots. No approximation is silently labeled as truth."""

import json
from pathlib import Path

import numpy as np
from astropy.io import fits

from .integrity import publish_directory


def _plt():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ValueError("install OSP with the diagnostics extra to create plots") from exc
    return plt


def _image(ax, values, label, *, fixed=None):
    finite = values[np.isfinite(values)]
    if not finite.size:
        ax.set_title(f"{label} (unavailable)")
        return None
    lo, hi = fixed if fixed is not None else np.percentile(finite, (2, 98))
    ax.set_title(label)
    return ax.imshow(values, origin="lower", vmin=lo, vmax=hi, cmap="viridis")


def _exposure(plt, folder, report, reference):
    quality = report["quality"]
    path = Path(report["path"])
    with fits.open(path, memmap=True) as hdus:
        science = np.asarray(hdus["SCI"].data, dtype=float)
        unit = hdus["SCI"].header.get("BUNIT")
        sim = hdus[0].header.get("SIMULATE") is True
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout="constrained")
    image = _image(axes[0, 0], science, "Science and detected sources")
    if image is not None:
        fig.colorbar(image, ax=axes[0, 0], label=unit)
    sources = quality.get("sources", [])
    if sources:
        axes[0, 0].scatter(
            [r["x"] for r in sources],
            [r["y"] for r in sources],
            s=42,
            facecolors="none",
            edgecolors="orange",
        )
        axes[1, 0].hist([r["fwhm"] for r in sources], bins="auto")
        axes[1, 1].hist([r["ellipticity"] for r in sources], bins="auto")
    axes[1, 0].set(xlabel="FWHM (pixel)", ylabel="Source count")
    axes[1, 1].set(xlabel="Ellipticity (1 − b/a)", ylabel="Source count")
    if quality.get("background_grid"):
        background = np.asarray(quality["background_grid"], dtype=float)
        tile_map = _image(axes[0, 1], background, "Measured background by tile")
        if tile_map is not None:
            fig.colorbar(tile_map, ax=axes[0, 1], label=unit)
    else:
        axes[0, 1].set_title("Background unavailable")
    fig.savefig(folder / "quality.png", dpi=120)
    plt.close(fig)
    if reference is not None:
        with fits.open(reference, memmap=True) as hdus:
            hdu = hdus["SCI"] if "SCI" in hdus else hdus[0]
            if hdu.data.shape != science.shape or hdu.header.get("BUNIT") != unit:
                raise ValueError("residual reference must match the science shape and BUNIT")
            if (hdus[0].header.get("SIMULATE") is True) != sim:
                raise ValueError("simulation flags differ between product and reference")
            residual = science - hdu.data
        fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
        residual_map = _image(axes[0], residual, "SCI minus independent reference")
        if residual_map is not None:
            fig.colorbar(residual_map, ax=axes[0], label=unit)
        finite = residual[np.isfinite(residual)]
        if finite.size:
            axes[1].hist(finite, bins=60)
        axes[1].set(xlabel=f"Residual ({unit})", ylabel="Pixel count")
        fig.savefig(folder / "calibration-residuals.png", dpi=120)
        plt.close(fig)
    residuals = report["astrometry"].get("residuals", [])
    if residuals:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
        for group, keep in (("Accepted matches", True), ("Rejected matches", False)):
            points = [r for r in residuals if r["inlier"] is keep]
            if points:
                x, y, east, north = np.array(
                    [(r["x"], r["y"], r["east_arcsec"], r["north_arcsec"]) for r in points]
                ).T
                axes[0].scatter(east, north, label=group, s=17)
                field = axes[1].scatter(
                    x,
                    y,
                    c=np.hypot(east, north),
                    label=group,
                    s=24,
                    cmap="magma",
                    vmin=0,
                    vmax=max(np.hypot(r["east_arcsec"], r["north_arcsec"]) for r in residuals) or 1,
                )
        axes[0].set(xlabel="East residual (arcsec)", ylabel="North residual (arcsec)")
        axes[0].legend()
        axes[1].set(xlabel="Detector x (pixel)", ylabel="Detector y (pixel)")
        fig.colorbar(field, ax=axes[1], label="Radial residual (arcsec)")
        fig.savefig(folder / "astrometry-residuals.png", dpi=120)
        plt.close(fig)


def _master(plt, folder, master):
    with master.images() as planes:
        fig, axes = plt.subplots(2, 2, figsize=(10, 7), layout="constrained")
        h = int(planes["DATA"].hdu.header["NAXIS2"])
        for ax, name, title in zip(
            axes.flat,
            ("DATA", "VAR", "COUNT", "REJECT"),
            ("Master", "Estimator variance", "Contributing samples", "Rejected samples"),
            strict=True,
        ):
            img = _image(ax, planes[name].rows(0, h), title)
            if img is not None:
                fig.colorbar(img, ax=ax)
        fig.savefig(folder / "master-quality.png", dpi=120)
        plt.close(fig)


def _evidence(plt, folder, rows, name):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    if name == "uncertainty":
        x = [r["signal_e"] for r in rows]
        for key, label in (("within_1err", "±1 ERR"), ("within_1_96err", "±1.96 ERR")):
            y = np.asarray([r[key] for r in rows])
            n = np.asarray([r["trials"] for r in rows])
            axes[0].errorbar(x, y, yerr=1.96 * np.sqrt(y * (1 - y) / n), marker="o", label=label)
        axes[0].set(xlabel="Injected signal (electron)", ylabel="Measured coverage")
        axes[0].legend()
        for key, label in (
            ("empirical_variance_over_analytic", "Empirical"),
            ("mean_osp_variance_over_analytic", "OSP"),
        ):
            axes[1].plot(x, [r[key] for r in rows], marker="o", label=label)
        axes[1].set(xlabel="Injected signal (electron)", ylabel="Variance / analytic variance")
    else:
        for row in rows:
            label = f"{row['workers']} worker(s)"
            axes[0].scatter(row["count"], row["elapsed_s"], label=label)
            axes[1].scatter(row["count"], row["peak_sum_mib"], label=label)
        axes[0].set(xlabel="Exposures", ylabel="Wall time (s)")
        axes[1].set(xlabel="Exposures", ylabel="Peak sampled process RSS (MiB)")
    handles, labels = axes[1].get_legend_handles_labels()
    unique = dict(zip(labels, handles, strict=True))
    axes[1].legend(unique.values(), unique.keys())
    fig.savefig(folder / f"{name}.png", dpi=120)
    plt.close(fig)


def generate(
    output: Path, *, report=None, master=None, reference=None, uncertainty=None, benchmark=None
) -> list[str]:
    """Atomically publish plots with real data available for the selected target."""
    if output.exists():
        raise FileExistsError(f"plot output already exists: {output}")
    plt = _plt()
    with publish_directory(output) as temp:
        if report is not None:
            _exposure(plt, temp, report, reference)
        if master is not None:
            _master(plt, temp, master)
        if uncertainty is not None:
            rows = json.loads(uncertainty.read_text(encoding="utf-8-sig"))["low_counts"]
            _evidence(plt, temp, rows, "uncertainty")
        if benchmark is not None:
            rows = [
                json.loads(line)
                for line in benchmark.read_text(encoding="utf-8-sig").splitlines()
                if line.strip()
            ]
            _evidence(plt, temp, [r for r in rows if "count" in r], "batch-performance")
        result = sorted(p.name for p in temp.glob("*.png"))
        if not result:
            raise ValueError("choose at least one plot input")
    return [str(output / name) for name in result]
