"""Regenerate isolated calibrators and compare independent matched-dark reductions."""

import argparse
import json
import statistics
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.nddata import CCDData, VarianceUncertainty

from ohobs_pipeline.config import Config
from ohobs_pipeline.ingest import inspect_frame
from ohobs_pipeline.masters import build_master
from ohobs_pipeline.origin import stamp_origin
from ohobs_pipeline.reduction import apply_calibration

GAIN = 2.0  # Injected simulation parameter, unrelated to the OHOBS camera.


def create(root):
    rng = np.random.default_rng(93941)
    yy, xx = np.indices((32, 40))
    response = 0.82 + 0.36 * xx / 39
    ds = 12 + 14 * (xx == 2) + 0.4 * yy
    truth = 120 + 500 * np.exp(-((xx - 20.3) ** 2 + (yy - 13.1) ** 2) / 8)
    offset = 700 + 0.4 * yy + 1.5 * np.sin(xx / 8)
    files = {}
    for role, duration, count, actual in [
        ("DARK", 120, 24, ds),
        ("FLAT_DARK", 3.75875, 24, ds * 0.03),
        ("FLAT", 3.75875, 24, 33000 * response + ds * 0.03),
        ("LIGHT", 120, 1, GAIN * truth * response + ds),
    ]:
        directory = root / role.lower()
        directory.mkdir()
        files[role] = []
        for i in range(count):
            signal = offset + (rng.poisson(actual) + rng.normal(0, 4, xx.shape)) / GAIN
            h = fits.PrimaryHDU(signal)
            stamp_origin(h.header, ("osp-reference-fixture", "1"))
            h.header.update(
                {
                    "INSTRUME": "OSP Synthetic",
                    "CAMERAID": "OSP-SIM-REFERENCE",
                    "READOUTM": "Full",
                    "GAIN": 30,
                    "OFFSET": 30,
                    "XBINNING": 1,
                    "YBINNING": 1,
                    "XORGSUBF": 0,
                    "YORGSUBF": 0,
                    "BUNIT": "adu",
                    "CCD-TEMP": 18.9,
                    "IMAGETYP": role,
                    "FILTER": "synthetic-Ha",
                    "OPTICID": "simulator",
                    "EXPTIME": duration,
                    "DATE-OBS": "2026-01-01T00:00:00",
                }
            )
            path = directory / f"synthetic-{role.lower()}-{i:02}.fits"
            h.writeto(path, checksum=True)
            files[role].append(path)
    return files, truth, (xx - 20.3) ** 2 + (yy - 13.1) ** 2 < 49


def reference(darks, short, flats, raw):
    d, fd, f = [np.mean(a, axis=0) for a in (darks, short, flats)]
    temporal = np.var(darks, axis=0, ddof=1)
    norm = float(np.median(f - fd))
    vf = (
        np.var(flats, axis=0, ddof=1) / len(flats) + np.var(short, axis=0, ddof=1) / len(short)
    ) / norm**2

    def ccd(data, var, unit="adu"):
        return CCDData(data, unit=unit, uncertainty=VarianceUncertainty(var))

    r, dm = ccd(raw, temporal + np.maximum(raw - d, 0) / GAIN), ccd(d, temporal / len(darks))
    fm = ccd((f - fd) / norm, vf, "")
    try:
        import ccdproc
    except ImportError:
        label = "Astropy CCDData (ccdproc unavailable)"
        answer = r.subtract(dm).divide(fm)
    else:
        from astropy import units as u

        label = "ccdproc " + ccdproc.__version__
        answer = ccdproc.flat_correct(
            ccdproc.subtract_dark(
                r,
                dm,
                dark_exposure=120 * u.s,
                data_exposure=120 * u.s,
                scale=False,
                add_keyword=False,
            ),
            fm,
            norm_value=1.0,
            add_keyword=False,
        )
    results = {"established_workflow": (answer.data, answer.uncertainty.array)}
    nd, nf, ns = len(darks), len(flats), len(short)
    data, error, stats = np.empty(raw.shape), np.empty(raw.shape), []
    for i, j in np.ndindex(raw.shape):
        a, b, c = ([float(x) for x in group[:, i, j]] for group in (darks, short, flats))
        stats.append(
            (
                i,
                j,
                statistics.mean(a),
                statistics.mean(c) - statistics.mean(b),
                statistics.variance(a),
                statistics.variance(b) / ns + statistics.variance(c) / nf,
            )
        )
    scale = statistics.median(p[3] for p in stats)
    for i, j, baseline, illumination, noise, variance in stats:
        diff, flat = float(raw[i, j]) - baseline, illumination / scale
        data[i, j] = diff / flat
        error[i, j] = (max(0.0, diff) / GAIN + noise * (1 + 1 / nd)) / flat**2 + (
            diff / flat**2
        ) ** 2 * variance / scale**2
    results["independent_scalar_arithmetic"] = (data, error)
    return label, results


def run(root):
    files, truth, aperture = create(root)
    config = Config.model_validate(
        {
            "node": "SYNTHETIC",
            "synthetic_test": True,
            "work_dir": root / "work",
            "detector": {
                "gain_e_per_adu": GAIN,
                "evidence": "injected simulation",
                "characterized_settings": {
                    "camera": "OSP-SIM-REFERENCE",
                    "readout": "Full",
                    "gain": 30,
                    "offset": 30,
                    "bin_x": 1,
                    "bin_y": 1,
                    "unit": "adu",
                    "temperature_min_c": 18.9,
                    "temperature_max_c": 18.9,
                },
            },
        }
    )
    dark = build_master(files["DARK"], config)
    short = build_master(files["FLAT_DARK"], config)
    flat = build_master(files["FLAT"], config, flat_dark_id=short.id)
    ours = apply_calibration(inspect_frame(files["LIGHT"][0], config), dark, flat, config)
    arrays = {k: np.array([fits.getdata(p) for p in v]) for k, v in files.items()}
    label, refs = reference(arrays["DARK"], arrays["FLAT_DARK"], arrays["FLAT"], arrays["LIGHT"][0])
    z = (ours.science - truth) / np.sqrt(ours.variance)
    result = {
        "reference_package": label,
        "pixel_count": ours.science.size,
        "aperture_pixels": int(aperture.sum()),
        "truth_aperture_adu": float((truth[aperture] - 120).sum()),
        "osp_aperture_adu": float((ours.science[aperture] - 120).sum()),
        "normalized_residual_mean": float(z.mean()),
        "normalized_residual_sd": float(z.std(ddof=1)),
        "coverage_1sigma": float(np.mean(np.abs(z) <= 1)),
        "coverage_1_96sigma": float(np.mean(np.abs(z) <= 1.96)),
        "comparisons": {},
    }
    for key, (science, var) in refs.items():
        delta = ours.science - science
        h, w = delta.shape
        result["comparisons"][key] = {
            "max_abs_difference_adu": float(np.max(np.abs(delta))),
            "rms_difference_adu": float(np.sqrt(np.mean(delta**2))),
            "aperture_difference_adu": float(delta[aperture].sum()),
            "max_abs_uncertainty_difference_adu": float(
                np.max(np.abs(np.sqrt(ours.variance) - np.sqrt(var)))
            ),
            "max_abs_row_mean_adu": float(np.max(np.abs(np.mean(delta, axis=1)))),
            "quadrant_mean_difference_adu": [
                float(np.mean(delta[i : i + h // 2, j : j + w // 2]))
                for i in (0, h // 2)
                for j in (0, w // 2)
            ],
        }
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path, help="new directory for synthetic inputs and products")
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    print(json.dumps(run(a.output), indent=2))
