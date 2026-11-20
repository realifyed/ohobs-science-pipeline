import numpy as np
from conftest import frame_file, settings

from ohobs_pipeline.characterization import characterize
from ohobs_pipeline.config import Config


def test_paired_photon_transfer(tmp_path):
    rng = np.random.default_rng(9821)
    shape = (140, 160)
    gain, noise = 2.0, 4.0
    fixed = np.broadcast_to(np.linspace(0, 80, shape[1]), shape)
    response = np.broadcast_to(np.linspace(0.92, 1.08, shape[0])[:, None], shape)
    levels = []

    def write(kind, exp, suffix, electrons):
        raw = (
            430
            + fixed
            + (rng.poisson(electrons, size=shape) + rng.normal(0, noise, size=shape)) / gain
        )
        return str(frame_file(tmp_path / f"{kind}-{exp}-{suffix}.fits", raw, kind, exp))

    for exp in (1, 2, 4, 6, 10):
        signal = min(exp, 8) * 500 * response
        levels.append(
            {
                "flat": [write("FLAT", exp, i, signal + exp) for i in range(2)],
                "dark": [write("DARK", exp, i, exp) for i in range(2)],
                "fit": exp < 10,
            }
        )
    biases = [write("BIAS", 0, i, 0) for i in range(2)]
    result = characterize(
        {"levels": levels, "bias_pair": biases}, Config.model_validate(settings(tmp_path))
    )
    assert abs(result["gain_e_per_adu"] / gain - 1) < 0.04
    assert abs(result["read_noise_e"] / noise - 1) < 0.05
    assert result["points"][-1]["linearity_fractional_residual"] < -0.18
    assert result["saturation_adu"] is None
