"""Exercise the installed production CLI and FITS product API on a frozen fixture."""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path
from zipfile import ZipFile

from astropy.io import fits

from ohobs_pipeline.integrity import digest, read_json
from ohobs_pipeline.origin import classify_origin
from ohobs_pipeline.products import validate_product


def run(root: Path, with_simulation: bool) -> dict:
    scripts = Path(sys.executable).parent
    osp = scripts / ("osp.exe" if os.name == "nt" else "osp")
    sim = scripts / ("osp-sim.exe" if os.name == "nt" else "osp-sim")
    assert sim.is_file() == with_simulation
    assert (importlib.util.find_spec("ohobs_sim") is not None) == with_simulation
    metadata = distribution("ohobs-science-pipeline")
    assert all("ohobs-science-sim" not in spec for spec in metadata.requires or [])
    if not with_simulation:
        assert importlib.util.find_spec("matplotlib") is None

    def call(*args):
        proc = subprocess.run(
            [str(osp), *map(str, args)], text=True, capture_output=True, check=False
        )
        if proc.returncode:
            raise RuntimeError(proc.stderr or proc.stdout)
        return proc.stdout

    help_text = call("--help")
    assert "simulate" not in help_text
    assert all(
        command in help_text
        for command in ("doctor", "reduce", "batch", "masters", "qc", "astrometry", "validate")
    )
    assert json.loads(call("doctor"))
    migrated = subprocess.run([str(osp), "simulate"], capture_output=True, text=True, check=False)
    assert migrated.returncode == 2 and "osp-sim generate" in migrated.stderr
    if with_simulation:
        subprocess.run([str(sim), "--help"], check=True, capture_output=True)
        manifests = []
        for path in (root, root.with_name("repeat")):
            args = [
                str(sim),
                "generate",
                "--height",
                "32",
                "--width",
                "40",
                "--lights",
                "1",
                "--masters",
                "5",
                "--output",
                str(path),
            ]
            manifests.append(json.loads(subprocess.check_output(args, text=True)))
        assert manifests[0] == manifests[1]
    else:
        fixture = Path(__file__).resolve().parents[1] / "examples" / "core-smoke-fixture.zip"
        with ZipFile(fixture) as archive:
            archive.extractall(root)
    manifest = read_json(root / "manifest.json")
    for name, expected in manifest["checksums"].items():
        assert digest(root / name) == expected, name
    config = root / "simulation.yaml"
    masters = {}
    for role, directory in (("DARK", "dark"), ("FLAT_DARK", "flat_dark"), ("FLAT", "flat")):
        correction = ["--flat-dark", masters["FLAT_DARK"]] if role == "FLAT" else []
        masters[role] = json.loads(
            call(
                "masters",
                "build",
                "--config",
                config,
                "--kind",
                role,
                *correction,
                *sorted((root / directory).glob("*.fits")),
            )
        )["id"]
    raw = root / "light/light-00000.fits"
    assert (
        json.loads(call("fits", "inspect", raw, "--config", config))["metadata"]["kind"] == "LIGHT"
    )
    result = json.loads(call("reduce", raw, "--config", config))
    product = Path(result["path"])
    assert json.loads(call("qc", product, "--config", config))
    report = json.loads(call("report", "--product", product, "--html", root / "exposure.html"))
    assert report["integrity"] == "VERIFIED" and (root / "exposure.html").is_file()
    assert json.loads(call("validate", product)) == json.loads(
        json.dumps(validate_product(product))
    )
    with fits.open(product) as hdus:
        assert [h.name for h in hdus] == ["PRIMARY", "SCI", "ERR", "DQ"]
        generator = manifest["generator"]
        assert classify_origin(hdus[0].header) == (generator["id"], generator["version"])
    manifest = read_json(product.parent / "provenance.json")
    assert manifest["definition"]["input_sha256"] == digest(raw)
    assert manifest["definition"]["masters"]["dark"]["id"] == masters["DARK"]
    return {
        "with_simulation": with_simulation,
        "product_status": result["state"],
        "provenance_verified": True,
        "independent_core_cli": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--with-simulation", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.with_simulation), indent=2))
