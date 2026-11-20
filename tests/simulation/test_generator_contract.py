"""Unit tests for the optional generator command and its FITS origin."""

import json

import pytest
from astropy.io import fits

from ohobs_pipeline.origin import classify_origin

main = pytest.importorskip("ohobs_sim.cli").main
GENERATOR_ORIGIN = pytest.importorskip("ohobs_sim.generator").GENERATOR_ORIGIN

pytestmark = pytest.mark.simulation


def test_adversarial_cli_marks_exposures_and_truth(tmp_path, capsys):
    target = tmp_path / "demo"
    assert (
        main(
            [
                "generate",
                "--output",
                str(target),
                "--profile",
                "adversarial",
                "--masters",
                "5",
                "--lights",
                "1",
                "--height",
                "32",
                "--width",
                "40",
            ]
        )
        == 0
    )
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["generator"] == {"id": GENERATOR_ORIGIN[0], "version": GENERATOR_ORIGIN[1]}
    assert (target / "faults/truncated.fits").exists()
    for path in target.rglob("*.fits"):
        if path.name != "truncated.fits":
            assert classify_origin(fits.getheader(path)) == GENERATOR_ORIGIN
