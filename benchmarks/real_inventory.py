"""Read-only OHOBS per-file inventory and detector-code diagnostics."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np

from ohobs_pipeline.ingest import inspect_frame

KEYS = (
    "SET-TEMP",
    "TELESCOP",
    "FOCALLEN",
    "ROWORDER",
    "USBLIMIT",
    "BITPIX",
    "BZERO",
    "BSCALE",
    "EGAIN",
    "BUNIT",
    "TIMESYS",
    "DATE-OBS",
    "MJD-OBS",
    "DATE-AVG",
    "MJD-AVG",
    "DATE-END",
    "RA",
    "DEC",
    "OBJECT",
    "SWCREATE",
    "XORGSUBF",
    "YORGSUBF",
    "OPTICID",
)


def inventory(root, output):
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in (".fits", ".fit", ".fts"))
    rows = []
    for path in files:
        f = inspect_frame(path)
        v = f.values
        hist = np.zeros(65536, dtype=np.int64)
        for start in range(0, f.shape[0], 128):
            with f.image() as image:
                tile = image.rows(start, min(start + 128, f.shape[0]))
            if not (
                np.isfinite(tile).all()
                and np.all((tile >= 0) & (tile < len(hist)))
                and np.all(tile == np.floor(tile))
            ):
                raise ValueError("inventory expects unsigned 16-bit physical codes")
            hist += np.bincount(tile.astype(np.int32).ravel(), minlength=len(hist))
        codes = np.flatnonzero(hist)
        row = {
            "path": path.relative_to(root).as_posix(),
            "sha256": f.sha256,
            **v,
            "nx": f.shape[1],
            "ny": f.shape[0],
            "utc_start": f.start,
            "utc_midpoint": f.midpoint,
            "raw_wcs": f.wcs_status,
            **{name: f.header.get(name) for name in KEYS},
            "min_code": int(codes[0]),
            "max_code": int(codes[-1]),
            "code_step_gcd": int(np.gcd.reduce(np.diff(codes))),
            "count_65520": int(hist[65520]),
            "median_code": int(np.searchsorted(np.cumsum(hist), (int(hist.sum()) + 1) // 2)),
            "obs_date_mjd_delta_ms": f.time_deltas_ms.get("DATE-OBS"),
            "avg_date_mjd_delta_ms": f.time_deltas_ms.get("DATE-AVG"),
        }
        rows.append(row)
    if not rows:
        raise ValueError("empty input")
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for group, n in sorted(
        Counter((r["kind"], r["filter"], r["exposure"], r["temp"]) for r in rows).items()
    ):
        selected = [r for r in rows if (r["kind"], r["filter"], r["exposure"], r["temp"]) == group]
        print(
            json.dumps(
                {
                    "group": group,
                    "frames": n,
                    "clip_candidates": sum(r["count_65520"] for r in selected),
                    "frames_at_65520": sum(r["count_65520"] > 0 for r in selected),
                    "median_range": [
                        min(r["median_code"] for r in selected),
                        max(r["median_code"] for r in selected),
                    ],
                }
            )
        )
    for key in ("camera", "model", "readout", "gain", "offset", "code_step_gcd", "nx", "ny", *KEYS):
        if key not in ("DATE-OBS", "MJD-OBS", "DATE-AVG", "MJD-AVG", "RA", "DEC"):
            print(key, dict(Counter(str(r[key]) for r in rows)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    inventory(a.root, a.output)
