"""Generate a controlled field and report calibration and source recovery."""

import argparse
import json
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table
from ohobs_sim.generator import Simulation, generate_dataset

from ohobs_pipeline.config import load_config
from ohobs_pipeline.masters import build_master
from ohobs_pipeline.pipeline import reduce_exposure
from ohobs_pipeline.products import read_calibrated
from ohobs_pipeline.reporting import exposure_report


def validate(root: Path) -> dict:
    parameters = Simulation.model_validate({"masters": 16, "lights": 3})
    generation = generate_dataset(root, parameters, adversarial=True)
    config = load_config(root / "simulation.yaml")
    dark = build_master(sorted((root / "dark").glob("*.fits")), config)
    short = build_master(sorted((root / "flat_dark").glob("*.fits")), config)
    flat = build_master(sorted((root / "flat").glob("*.fits")), config, flat_dark_id=short.id)
    truth = fits.getdata(root / "truth.fits")
    response = fits.getdata(root / "truth.fits", "RESPONSE")
    expected = truth * np.median(response) / parameters.gain
    sources = Table.read(root / "truth.ecsv")
    xy = np.column_stack((sources["x"], sources["y"]))
    yy, xx = np.indices(expected.shape)
    results = []
    for path in sorted((root / "light").glob("*.fits")):
        receipt = reduce_exposure(path, config, dark_id=dark.id, flat_id=flat.id)
        product = Path(receipt["path"])
        data = read_calibrated(product)
        report = exposure_report(product)
        residual = data.science - expected
        z = residual / np.sqrt(data.variance)
        z = z[np.isfinite(z)]
        fits_xy = np.asarray([(s["x"], s["y"]) for s in report["quality"]["sources"]])
        nearest = np.min(np.linalg.norm(fits_xy[:, None] - xy[None], axis=2), axis=1)
        # Measure aperture disagreement against the same fixed truth apertures.
        # The denominator uses the injected total stellar flux and avoids
        # fitting the reduction's sky as a reference.
        flux_errors = []
        for source in sources:
            aperture = (xx - source["x"]) ** 2 + (yy - source["y"]) ** 2 <= 16
            scale = source["flux_e"] * np.median(response) / parameters.gain
            flux_errors.append(float(np.nansum(residual[aperture]) / scale))
        results.append(
            {
                "input": path.name,
                "product_state": receipt["state"],
                "pixels": len(z),
                "mean_bias_adu": float(np.nanmean(residual)),
                "rms_adu": float(np.sqrt(np.nanmean(residual**2))),
                "median_row_bias_adu": float(np.nanmedian(np.nanmean(residual, axis=1))),
                "normalized_sd": float(np.std(z)),
                "coverage_1sigma": float(np.mean(np.abs(z) <= 1)),
                "coverage_1_96sigma": float(np.mean(np.abs(z) <= 1.96)),
                "centroid_median_px": float(np.median(nearest)),
                "sources": len(nearest),
                "median_aperture_fractional_error": float(np.median(flux_errors)),
                "fwhm_px": report["quality"]["fwhm_px"],
                "ellipticity": report["quality"]["ellipticity"],
            }
        )
    return {
        "seed": parameters.seed,
        "generated_files": len(generation["checksums"]),
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(validate(parser.parse_args().output), indent=2, allow_nan=False))
