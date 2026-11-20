"""Version 1 of the OSP pixel quality convention."""

from enum import IntFlag

import numpy as np
from scipy.ndimage import maximum_filter, median_filter, minimum_filter

from .config import Config
from .ingest import Frame


class DQ(IntFlag):
    NONFINITE = 0x0001
    SATURATED = 0x0002
    BAD_PIXEL = 0x0004
    HOT_PIXEL = 0x0008
    DEAD_PIXEL = 0x0010
    FLAT_INVALID = 0x0020
    COSMIC_RAY_CANDIDATE = 0x0040
    EDGE = 0x0080
    INTERPOLATED = 0x0100
    CALIBRATION_SUSPECT = 0x0200
    NONLINEAR_RESPONSE = 0x0400


FATAL = int(
    DQ.NONFINITE
    | DQ.SATURATED
    | DQ.BAD_PIXEL
    | DQ.HOT_PIXEL
    | DQ.DEAD_PIXEL
    | DQ.FLAT_INVALID
    | DQ.CALIBRATION_SUSPECT
    | DQ.NONLINEAR_RESPONSE
)


def characterized(frame: Frame, config: Config) -> bool:
    settings = config.detector.characterized_settings
    if not config.detector.evidence or frame.values["temp"] is None or not settings:
        return False
    return all(
        frame.values.get(k) == v
        for k, v in settings.items()
        if k not in {"temperature_min_c", "temperature_max_c"}
    ) and float(settings["temperature_min_c"]) <= frame.values["temp"] <= float(
        settings["temperature_max_c"]
    )


def raw_mask(data, frame: Frame, config: Config, row: int = 0):
    mask = np.zeros(data.shape, dtype=np.uint16)
    mask[~np.isfinite(data)] |= int(DQ.NONFINITE)
    if characterized(frame, config):
        sat, linear = config.detector.saturation, config.detector.linear_max
        if sat is not None:
            mask[data >= sat] |= int(DQ.SATURATED)
        if linear is not None:
            mask[data > linear] |= int(DQ.NONLINEAR_RESPONSE)
    detector = config.detector
    maps = (
        (DQ.BAD_PIXEL, detector.bad_pixels_yx),
        (DQ.HOT_PIXEL, detector.hot_pixels_yx),
        (DQ.DEAD_PIXEL, detector.dead_pixels_yx),
    )
    for bit, coordinates in maps:
        for y, x in coordinates:
            if row <= y < row + data.shape[0] and 0 <= x < data.shape[1]:
                mask[y - row, x] |= int(bit)
    return mask


def flag_cosmic_candidates(science, variance, dq, sigma: float) -> int:
    """Flag strong isolated positive impulses using local medians and valid ERR.

    This screening flag can include hot pixels or undersampled sources. Pixels
    are preserved. The mask prevents their neighborhoods from driving QC fits.
    """
    if min(science.shape) < 5:
        return 0
    valid = (dq == 0) & np.isfinite(science) & np.isfinite(variance) & (variance > 0)
    values = np.where(valid, science, 0.0)
    local = median_filter(values, size=5, mode="nearest")
    cross = np.ones((3, 3), dtype=bool)
    cross[1, 1] = False
    neighbors = maximum_filter(values, footprint=cross, mode="nearest")
    candidate = valid & (science - local > sigma * np.sqrt(variance))
    candidate &= science - neighbors > 0.75 * (science - local)
    candidate &= minimum_filter(valid, size=5, mode="nearest")
    candidate[[0, 1, -2, -1], :] = False
    candidate[:, [0, 1, -2, -1]] = False
    dq[candidate] |= int(DQ.COSMIC_RAY_CANDIDATE)
    return int(np.count_nonzero(candidate))
