"""Seeded detector and stellar-field simulation with versioned FITS truth."""

from pathlib import Path
from typing import Literal

import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS
from pydantic import Field

from ohobs_pipeline.config import Settings
from ohobs_pipeline.integrity import digest, publish_directory, write_json
from ohobs_pipeline.origin import classify_origin, stamp_origin

from . import __version__

PROFILES = ("standard", "high", "low", "zero", "defects", "crowded")
GENERATOR_ID = "ohobs-science-sim"
GENERATOR_ORIGIN = (GENERATOR_ID, __version__)


def _write_fits(path: Path, *hdus) -> None:
    stamp_origin(hdus[0].header, GENERATOR_ORIGIN)
    for hdu in hdus:
        for key in ("CHECKSUM", "DATASUM"):
            if key in hdu.header:
                del hdu.header[key]
        hdu.add_checksum(when="Seeded OSP simulation")
    fits.HDUList(list(hdus)).writeto(path)
    with fits.open(path, memmap=True, do_not_scale_image_data=True) as written:
        written.verify("exception")
        if classify_origin(*(hdu.header for hdu in written)) != GENERATOR_ORIGIN:
            raise ValueError("generated FITS lost its synthetic origin")


class Simulation(Settings):
    """Synthetic detector parameters. Electron-domain values are per pixel."""

    profile: Literal["standard", "high", "low", "zero", "defects", "crowded"] = "standard"
    seed: int = Field(1234, ge=0)
    height: int = Field(96, ge=32, le=4096)
    width: int = Field(128, ge=32, le=4096)
    lights: int = Field(3, ge=1, le=5000)
    masters: int = Field(12, ge=5, le=300)
    gain: float = Field(1.6, gt=0)
    read_noise_e: float = Field(3.5, ge=0)
    bias_adu: float = Field(900, gt=0)
    dark_e_s: float = Field(0.12, ge=0)
    dark_doubling_c: float = Field(6, gt=0)
    temperature_c: float = Field(-10, ge=-60, le=30)
    saturation_adu: int = Field(60000, ge=100, le=65535)
    quantization_adu: int = Field(1, ge=1, le=256)
    nonlinearity: float = Field(0, ge=0, le=0.2)


def _scene(p, rng, x, y):
    h, w = x.shape
    scene = np.zeros_like(x)
    rows: list[tuple] = []
    scale = {"high": 3.0, "low": 0.035, "zero": 0.0}.get(p.profile, 1.0)
    if scale:
        scene += scale * (
            55
            + 25 * x / w
            + 75 * np.exp(-(((x / w - 0.63) / 0.18) ** 2 + ((y / h - 0.4) / 0.24) ** 2))
        )
        for j, cy in enumerate(np.linspace(10, h - 11, 4)):
            for i, cx in enumerate(np.linspace(10, w - 11, 5)):
                cx, cy_star = cx + rng.uniform(-1, 1), cy + rng.uniform(-1, 1)
                sigma_x, sigma_y = 1.25 + 0.1 * (i % 3), 1.35 + 0.12 * (j % 3)
                if p.profile == "crowded":
                    sigma_x *= 1.65
                flux = float(rng.uniform(5000, 13000) * scale)
                if p.profile == "defects" and i == j == 1:
                    flux = 4_000_000.0
                psf = np.exp(-0.5 * (((x - cx) / sigma_x) ** 2 + ((y - cy_star) / sigma_y) ** 2))
                scene += flux * psf / psf.sum()
                rows.append((cx, cy_star, flux, sigma_x, sigma_y))
                if p.profile == "crowded":
                    shifted = np.exp(
                        -0.5 * (((x - cx - 3) / sigma_x) ** 2 + ((y - cy_star) / sigma_y) ** 2)
                    )
                    scene += 0.4 * flux * shifted / shifted.sum()
                    rows.append((cx + 3, cy_star, 0.4 * flux, sigma_x, sigma_y))
    return scene, rows


def generate_dataset(
    output: Path, parameters: Simulation | None = None, *, adversarial: bool = False
) -> dict:
    """Publish a synthetic dataset atomically. Pixel truth is in electrons."""
    p = parameters or Simulation.model_validate({})
    if output.exists():
        raise FileExistsError(f"simulation output already exists: {output}")
    if p.saturation_adu <= p.bias_adu:
        raise ValueError("saturation must exceed the electronic offset")
    if saturated_code(p) <= p.bias_adu:
        raise ValueError("quantized saturation must exceed the electronic offset")
    rng = np.random.default_rng(p.seed)
    h, w = p.height, p.width
    y, x = np.indices((h, w), dtype=float)
    truth, rows = _scene(p, rng, x, y)
    sky = WCS(naxis=2)
    sky.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    sky.wcs.crval = [268.1, -24.2]
    sky.wcs.crpix = [(w + 1) / 2, (h + 1) / 2]
    sky.wcs.cdelt = [-1.07 / 3600, 1.07 / 3600]
    sky.wcs.radesys = "ICRS"
    response = (1 - 0.2 * ((2 * x / (w - 1) - 1) ** 2 + (2 * y / (h - 1) - 1) ** 2)) * rng.uniform(
        0.96, 1.04, (h, w)
    )
    dark_rate = p.dark_e_s * (1 + 0.5 * x / w + 0.8 * np.exp(-(((x / w - 0.91) / 0.12) ** 2)))
    offset = p.bias_adu + 3 * np.sin(2 * np.pi * y / h)
    defect = np.zeros((h, w), dtype=np.uint16)
    if p.profile == "defects":
        response[7, 8] = 0
        defect[7, 8] = 0x0010
        dark_rate[8, 7] += 35
        defect[8, 7] = 0x0008
    camera = f"OSP-SIM-{p.seed}-{p.profile}"
    default_header = {
        "INSTRUME": "OSP Synthetic",
        "CAMERAID": camera,
        "READOUTM": "Simulation",
        "GAIN": 1,
        "OFFSET": 1,
        "XBINNING": 1,
        "YBINNING": 1,
        "XORGSUBF": 0,
        "YORGSUBF": 0,
        "CCD-TEMP": p.temperature_c,
        "BUNIT": "adu",
        "FILTER": "SYNTHETIC",
        "OPTICID": "OSP-SIM",
        "DATE-OBS": "2026-01-01T00:00:00",
        "TIMESYS": "UTC",
    }

    def frame(path, kind, exposure, index, illumination=0, **overrides):
        temperature = overrides.get("CCD-TEMP", p.temperature_c)
        thermal = dark_rate * 2 ** ((temperature + 10) / p.dark_doubling_c) * exposure
        electrons = rng.poisson(thermal + illumination * response)
        signal = (electrons + rng.normal(0, p.read_noise_e, (h, w))) / p.gain
        if p.profile == "defects" and kind == "LIGHT":
            signal[h // 2, w // 2] += 20000
        if p.nonlinearity:
            fraction = np.clip(signal / (p.saturation_adu - p.bias_adu), 0, 1)
            signal *= 1 - p.nonlinearity * fraction**2
        codes = np.rint((offset + signal) / p.quantization_adu) * p.quantization_adu
        saturated = min(65535, p.saturation_adu // p.quantization_adu * p.quantization_adu)
        header = fits.Header(default_header)
        header.update({"IMAGETYP": kind, "EXPTIME": exposure, "SIMINDEX": index, **overrides})
        _write_fits(path, fits.PrimaryHDU(np.clip(codes, 0, saturated).astype(np.uint16), header))

    with publish_directory(output) as temp:
        for group, kind, n, exposure, exposure_signal in (
            ("bias", "BIAS", p.masters, 0, 0),
            ("dark", "DARK", p.masters, 120, 0),
            ("flat_dark", "FLAT_DARK", p.masters, 4, 0),
            ("flat", "FLAT", p.masters, 4, 26000),
            ("light", "LIGHT", p.lights, 120, truth),
        ):
            directory = temp / group
            directory.mkdir()
            for i in range(n):
                frame(directory / f"{group}-{i:05d}.fits", kind, exposure, i, exposure_signal)
        truth_header = sky.to_header()
        truth_header["BUNIT"] = "electron"
        _write_fits(
            temp / "truth.fits",
            fits.PrimaryHDU(truth, truth_header),
            fits.ImageHDU(response, name="RESPONSE"),
            fits.ImageHDU(dark_rate, name="DARKRATE", header=fits.Header({"BUNIT": "electron/s"})),
            fits.ImageHDU(defect, name="DQ"),
        )
        catalogue = Table(
            rows=rows, names=("x", "y", "flux_e", "sigma_x_px", "sigma_y_px"), dtype=(float,) * 5
        )
        ra, dec = sky.pixel_to_world_values(catalogue["x"], catalogue["y"])
        catalogue["ra"], catalogue["dec"] = ra, dec
        catalogue.meta.update(synthetic=True, pixel_origin=0)
        catalogue.write(temp / "truth.ecsv", format="ascii.ecsv")
        Table(
            {
                "source_id": np.arange(len(catalogue)),
                "ra": ra,
                "dec": dec,
                "pmra": np.zeros(len(ra)),
                "pmdec": np.zeros(len(ra)),
                "ref_epoch": np.full(len(ra), 2016.0),
            }
        ).write(temp / "reference.ecsv", format="ascii.ecsv")
        write_json(
            temp / "simulation.yaml",
            {
                "node": "OSP-SIM",
                "synthetic_test": True,
                "work_dir": "work",
                "raw_dir": "light",
                "detector": {
                    "model": "OSP Synthetic",
                    "readout": "Simulation",
                    "gain_e_per_adu": p.gain,
                    "read_noise_e": p.read_noise_e,
                    "saturation": saturated_code(p),
                    "evidence": "seeded simulation, not camera measurements",
                    "characterized_settings": {
                        "camera": camera,
                        "readout": "Simulation",
                        "gain": 1,
                        "offset": 1,
                        "bin_x": 1,
                        "bin_y": 1,
                        "unit": "adu",
                        "temperature_min_c": p.temperature_c,
                        "temperature_max_c": p.temperature_c,
                    },
                    "hot_pixels_yx": [[8, 7]] if p.profile == "defects" else [],
                    "dead_pixels_yx": [[7, 8]] if p.profile == "defects" else [],
                },
                "quality": {"min_sources": 3, "max_sources": 100},
                "astrometry": {
                    "catalogue": "reference.ecsv",
                    "executable": "osp-absent-synthetic-solver",
                },
            },
        )
        if adversarial:
            _faults(temp, frame, sky, p)
        receipt = {
            "schema_version": 2,
            "synthetic": True,
            "generator": {"id": GENERATOR_ID, "version": __version__},
            "parameters": p.model_dump(mode="json"),
            "source_count": len(rows),
            "truth_signal_unit": "electron",
            "truth_positions_origin": 0,
            "checksums": {
                item.relative_to(temp).as_posix(): digest(item)
                for item in sorted(temp.rglob("*"))
                if item.is_file()
            },
        }
        write_json(temp / "manifest.json", receipt)
    return receipt


def saturated_code(p: Simulation) -> int:
    return p.saturation_adu // p.quantization_adu * p.quantization_adu


def _faults(temp, frame, sky, p):
    faults = temp / "faults"
    faults.mkdir()
    frame(faults / "saturated-flat.fits", "FLAT", 4, 0, 1e6)
    frame(faults / "invalid-flat.fits", "FLAT", 4, 0)
    frame(
        faults / "wrong-temperature-dark.fits", "DARK", 120, 0, **{"CCD-TEMP": p.temperature_c + 2}
    )
    frame(faults / "wrong-exposure-dark.fits", "DARK", 90, 0)
    raw = temp / "light" / "light-00000.fits"
    with fits.open(raw) as hdus:
        del hdus[0].header["CAMERAID"]
        _write_fits(faults / "missing-camera.fits", *hdus)
    with raw.open("rb") as stream:
        (faults / "truncated.fits").write_bytes(stream.read(3000))
    sky.wcs.crval = [300, 20]
    _write_fits(faults / "incorrect.wcs", fits.PrimaryHDU(header=sky.to_header()))
