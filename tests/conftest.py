from pathlib import Path

import numpy as np
import pytest
import yaml
from astropy.io import fits

from ohobs_pipeline.config import Config
from ohobs_pipeline.masters import build_master


def frame_file(path, data, role, exp, temp=-10.0, filter_name="Ha", **keys):
    path.parent.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(data)
    hdu.header.update(
        IMAGETYP=role,
        EXPTIME=exp,
        INSTRUME="Test mono",
        CAMERAID="T1",
        READOUTM="Full",
        GAIN=30,
        OFFSET=30,
        XBINNING=1,
        YBINNING=1,
        BUNIT="adu",
        FILTER=filter_name,
        OPTICID="tube+filter-wheel",
    )
    hdu.header["CCD-TEMP"] = temp
    hdu.header["XORGSUBF"] = hdu.header["YORGSUBF"] = 0
    hdu.header["DATE-OBS"] = "2024-07-01T00:00:00"
    hdu.header.update(keys)
    hdu.writeto(path)
    return path


def settings(path):
    return {
        "node": "test",
        "work_dir": str(path / "products and masters"),
        "workers": 2,
        "memory_mib": 128,
        "detector": {
            "gain_e_per_adu": 2.0,
            "read_noise_e": 4.0,
            "saturation": 62000.0,
            "linear_max": 60000.0,
            "evidence": "synthetic fixture by construction",
            "bad_pixels_yx": [[2, 2]],
            "characterized_settings": {
                "camera": "T1",
                "readout": "Full",
                "gain": 30,
                "offset": 30,
                "bin_x": 1,
                "bin_y": 1,
                "unit": "adu",
                "temperature_min_c": -10.0,
                "temperature_max_c": -10.0,
            },
        },
        "quality": {"min_sources": 2, "box": 24},
    }


@pytest.fixture
def dataset(tmp_path: Path):
    rng = np.random.default_rng(2341)
    options = settings(tmp_path)
    options["astrometry"] = {"executable": "nonexistent-osp-test-solver"}
    config = Config.model_validate(options)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(options), encoding="utf-8")
    shape = 72, 80
    y, x = np.indices(shape)
    bias = 1000 + 0.04 * y
    dark = 4 + 24 * np.exp(-((x - 2.0) ** 2 + (y - 20.0) ** 2) / 60.0)
    response = 0.8 + 0.4 * x / (shape[1] - 1)
    response[3, 3] = 0.001
    sky = np.full(shape, 170.0)
    for cx, cy in [(19, 20), (36, 35), (59, 51)]:
        sky += 700 * np.exp(-0.5 * (((x - cx - 0.2) / 1.8) ** 2 + ((y - cy + 0.15) / 1.3) ** 2))

    def dark_realization(factor):
        return bias + rng.poisson(2 * dark * factor) / 2 + rng.normal(0, 2, shape)

    def files(role, exp, make):
        return [
            frame_file(tmp_path / "cal" / f"{role}-{i}.fits", make(), role, exp) for i in range(24)
        ]

    d = build_master(files("DARK", 120, lambda: dark_realization(1)), config)
    fd = build_master(files("FLAT_DARK", 4, lambda: dark_realization(1 / 30)), config)
    f = build_master(
        files("FLAT", 4, lambda: dark_realization(1 / 30) + rng.poisson(24000 * response) / 2),
        config,
        flat_dark_id=fd.id,
    )
    raw = dark_realization(1) + rng.poisson(2 * sky * response) / 2
    raw[1, 0], raw[2, 1], raw[2, 3], raw[3, 1] = np.nan, 64000, 60900, 990.0
    light = frame_file(tmp_path / "observations folder" / "sample light.fits", raw, "LIGHT", 120)
    return {
        "config": config,
        "config_path": cfg_path,
        "dark": d,
        "flat": f,
        "flat_dark": fd,
        "light": light,
        "truth": sky,
        "raw": raw,
        "response": response,
        "bias": bias,
        "dark_signal": dark,
    }
