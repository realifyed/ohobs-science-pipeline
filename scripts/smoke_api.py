"""Independent installed-package API smoke covering generated truth to plotted products."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from astropy.io import fits
from astropy.time import Time
from ohobs_sim.generator import Simulation, generate_dataset

from ohobs_pipeline.astrometry import assess_candidate
from ohobs_pipeline.config import load_config
from ohobs_pipeline.masters import build_master
from ohobs_pipeline.origin import stamp_origin
from ohobs_pipeline.pipeline import reduce_exposure
from ohobs_pipeline.plots import generate
from ohobs_pipeline.products import read_calibrated, validate_product
from ohobs_pipeline.quality import Source
from ohobs_pipeline.reporting import exposure_report, write_html_report


def run(root: Path) -> dict:
    simulation = Simulation.model_validate({"lights": 1, "masters": 8})
    generated = generate_dataset(root, simulation)
    config = load_config(root / "simulation.yaml")
    dark = build_master(sorted((root / "dark").glob("*.fits")), config)
    short = build_master(sorted((root / "flat_dark").glob("*.fits")), config)
    flat = build_master(sorted((root / "flat").glob("*.fits")), config, flat_dark_id=short.id)
    path = root / "light/light-00000.fits"
    result = reduce_exposure(path, config, dark_id=dark.id, flat_id=flat.id)
    assert reduce_exposure(path, config, dark_id=dark.id, flat_id=flat.id)["id"] == result["id"]
    product = Path(result["path"])
    assert read_calibrated(product).science.shape == (96, 128)
    report = exposure_report(product)
    assert report["integrity"] == "VERIFIED" and report["quality"]["source_count"] > 0
    geometry = config.astrometry.model_copy(
        update={
            "max_rms_arcsec": 0.3,
            "min_matches": 5,
            "catalogue_independence_evidence": "injected WCS independent of detected centroids",
        }
    )
    sources = [Source(**row) for row in report["quality"]["sources"]]
    reference = root / "truth.fits"
    astrometry = assess_candidate(
        reference, (96, 128), sources[::3], Time("2026-01-01"), geometry
    ).report
    assert astrometry["status"] == "VERIFIED"

    def solve_known_field(sources, shape, epoch, settings, folder, *_args, **_kwargs):
        folder.mkdir()
        return assess_candidate(reference, shape, sources[::3], epoch, geometry)

    with patch("ohobs_pipeline.pipeline.astrometry.solve", solve_known_field):
        complete = reduce_exposure(
            path, config, dark_id=dark.id, flat_id=flat.id, revision="truth-wcs"
        )
    assert complete["state"] == "COMPLETE"
    solved_path = Path(complete["path"])
    assert validate_product(solved_path)["wcs"] == "VERIFIED"
    solved = read_calibrated(solved_path)
    completed_report = exposure_report(solved_path)
    assert completed_report["astrometry"]["status"] == "VERIFIED"
    assert completed_report["quality"]["status"] == "PASS"
    write_html_report(root / "exposure.html", completed_report)
    scaled = root / "expected-adu.fits"
    truth = fits.getdata(reference)
    response = fits.getdata(reference, "RESPONSE")
    truth_adu = truth * np.median(response) / simulation.gain
    normalized = (solved.science - truth_adu) / np.sqrt(solved.variance)
    assert abs(np.nanmedian(normalized)) < 0.12
    assert 0.88 < np.nanstd(normalized) < 1.16
    reference_header = fits.Header({"BUNIT": "adu"})
    stamp_origin(
        reference_header, (generated["generator"]["id"], generated["generator"]["version"])
    )
    fits.PrimaryHDU(truth_adu, reference_header).writeto(scaled)
    output = generate(root / "plots", report=completed_report, master=flat, reference=scaled)
    return {
        "generated_files": len(generated["checksums"]),
        "state": result["state"],
        "truth_wcs_product_state": complete["state"],
        "normalized_residual_sd": float(np.nanstd(normalized)),
        "quality": completed_report["quality"]["status"],
        "synthetic_wcs_matches": completed_report["astrometry"]["match_count"],
        "synthetic_wcs_rms_arcsec": completed_report["astrometry"]["rms_arcsec"],
        "plots": [Path(p).name for p in output],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(run(parser.parse_args().output), indent=2))
