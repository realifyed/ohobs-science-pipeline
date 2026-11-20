"""FITS input origin and reduction workflow policy."""

import re
from typing import Literal

from astropy.io import fits

ORIGIN_LABEL = "OSP Synthetic Generator"
ORIGIN_KEYS = ("SIMULATE", "ORIGIN", "SIMGEN", "SIMVER")
Origin = tuple[str, str] | Literal["observational"]


class FitsError(ValueError):
    """Unsupported, malformed or changed science input."""


class OriginError(FitsError):
    """Conflicting, incomplete or disallowed data origin."""


def classify_origin(*headers: fits.Header) -> Origin:
    """Check all relevant HDUs and duplicate cards for conflicting declarations."""
    values: dict[str, object] = {}
    labels = []
    for header in headers:
        for card in header.cards:
            key, value = card.keyword, card.value
            if key == "ORIGIN":
                labels.append(value)
            elif key in ORIGIN_KEYS:
                if key in values and (type(values[key]) is not type(value) or values[key] != value):
                    raise OriginError(f"contradictory FITS {key} cards")
                values[key] = value
    flag = values.get("SIMULATE", False)
    generator = values.get("SIMGEN")
    version = values.get("SIMVER")
    marked = (
        any(
            isinstance(label, str) and label.strip().casefold().startswith("osp synthetic")
            for label in labels
        )
        or "SIMGEN" in values
        or "SIMVER" in values
        or any(
            "SIMINDEX" in h
            or str(h.get("CAMERAID", "")).upper().startswith("OSP-SIM-")
            or str(h.get("INSTRUME", "")).strip().casefold() == "osp synthetic"
            or str(h.get("READOUTM", "")).strip().casefold() == "simulation"
            for h in headers
        )
    )
    if type(flag) is not bool:
        raise OriginError("FITS SIMULATE must be a logical value")
    if not flag and not marked:
        return "observational"
    if (
        flag is True
        and labels
        and all(label == ORIGIN_LABEL for label in labels)
        and isinstance(generator, str)
        and re.fullmatch(r"[a-z0-9][a-z0-9.-]{2,39}", generator)
        and isinstance(version, str)
        and re.fullmatch(r"[0-9][A-Za-z0-9.+!-]{0,31}", version)
    ):
        return generator, version
    raise OriginError(
        "incomplete or contradictory synthetic FITS identity (SIMULATE, ORIGIN, SIMGEN, SIMVER)"
    )


def require_workflow(origin: Origin, synthetic_test: bool) -> None:
    if origin != "observational" and not synthetic_test:
        raise OriginError("synthetic FITS require an explicit synthetic_test: true configuration")
    if origin == "observational" and synthetic_test:
        raise OriginError(
            "synthetic test workflow requires marked synthetic FITS, found an observational input"
        )


def stamp_origin(header: fits.Header, origin: Origin) -> None:
    if origin != "observational":
        header.update(SIMULATE=True, ORIGIN=ORIGIN_LABEL, SIMGEN=origin[0], SIMVER=origin[1])
