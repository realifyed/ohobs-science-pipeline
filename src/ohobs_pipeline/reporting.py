"""Read-only reports over validated products and persistent batch receipts."""

import json
from collections import Counter
from html import escape
from pathlib import Path

from .integrity import read_json
from .jobs import job_info
from .products import validate_product


def exposure_report(product: Path) -> dict:
    """Collect calibrated product provenance, QC and WCS measurements."""
    science = validate_product(product)
    root = product.parent
    return {
        "schema_version": 1,
        "kind": "exposure",
        "path": str(product),
        "integrity": "VERIFIED",
        **science,
        "quality": read_json(root / "qc.json"),
        "astrometry": read_json(root / "astrometry.json"),
        "provenance": read_json(root / "provenance.json"),
    }


def batch_report(work: Path, identifier: str) -> dict:
    """Summarize committed products and failure categories without changing jobs."""
    receipt = job_info(work, identifier, verify_products=True)
    qc: Counter[str] = Counter()
    astrometry: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    elapsed: list[float] = []
    for row in receipt["frames"]:
        outcome = row["outcome"] or {}
        if isinstance(duration := outcome.get("duration_s"), (int, float)):
            elapsed.append(duration)
        if row["state"] in {"FAILED", "QUARANTINED"}:
            failures[outcome.get("type") or outcome.get("kind") or "UNCLASSIFIED"] += 1
        if row.get("product_integrity", {}).get("status") == "VERIFIED":
            root = work / "products" / outcome["id"]
            qc[read_json(root / "qc.json")["status"]] += 1
            astrometry[read_json(root / "astrometry.json")["status"]] += 1
    return {
        "schema_version": 1,
        "kind": "batch",
        "id": identifier,
        "counts": receipt["counts"],
        "failure_categories": dict(failures),
        "quality": dict(qc),
        "astrometry": dict(astrometry),
        "integrity": receipt["product_integrity"],
        "worker_timing": {
            "count": len(elapsed),
            "total_s": sum(elapsed),
            "max_s": max(elapsed) if elapsed else None,
        },
        "memory": {"status": "NOT_COLLECTED", "benchmark": "benchmarks/batch_commission.py"},
    }


def write_html_report(path: Path, report: dict) -> None:
    """Create a standalone HTML view without scripting or network resources."""
    title = "OHOBS OSP " + report["kind"] + " report"
    body = escape(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    with path.open("x", encoding="utf-8") as stream:
        stream.write(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            f"<title>{escape(title)}</title><h1>{escape(title)}</h1><pre>{body}</pre></html>\n"
        )
