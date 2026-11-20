"""Fetch a public calibration field from Gaia TAP, then replay it offline."""

import argparse
import json
from pathlib import Path

from astropy.time import Time
from astropy.wcs import WCS

from ohobs_pipeline.config import Gaia
from ohobs_pipeline.gaia import GaiaError, reference


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    root = parser.parse_args().cache
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [100.5, 24.3]
    wcs.wcs.crpix = [64.5, 64.5]
    wcs.wcs.cdelt = [-1 / 3600, 1 / 3600]
    policy = Gaia(enabled=True, allow_network=True)
    epoch = Time("2026-01-01", scale="utc")
    try:
        path, record = reference(wcs, (128, 128), epoch, policy, root)
        again = reference(
            wcs, (128, 128), epoch, policy.model_copy(update={"allow_network": False}), root
        )
        assert again == (path, record)
    except (GaiaError, OSError) as exc:
        print(json.dumps({"status": "UNAVAILABLE", "reason": str(exc)}))
        return 1
    print(json.dumps({"status": "PASS", "rows": record["rows"], "sha256": record["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
