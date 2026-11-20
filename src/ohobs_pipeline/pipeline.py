"""Exposure orchestration and explicit publication states."""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from astropy.io import fits
from astropy.time import Time

from . import astrometry
from .config import Config
from .dq import characterized
from .events import Events
from .ingest import FitsError, inspect_frame
from .integrity import digest, identity, object_id, publish_directory, versions, write_json
from .masters import CalibrationError, reference_kind, select_master, verify_flat_lineage
from .products import validate_product, write_science
from .quality import measure
from .reduction import apply_calibration

TRANSITIONS = {
    "PENDING": {"VALIDATING"},
    "VALIDATING": {"CALIBRATING", "QUARANTINED", "FAILED"},
    "CALIBRATING": {"CALIBRATED", "FAILED"},
    "CALIBRATED": {"QC_RUNNING", "PARTIAL", "FAILED"},
    "QC_RUNNING": {"QC_COMPLETE", "PARTIAL", "FAILED"},
    "QC_COMPLETE": {"ASTROMETRY_RUNNING", "PARTIAL", "FAILED"},
    "ASTROMETRY_RUNNING": {"ASTROMETRY_VERIFIED", "PARTIAL", "FAILED"},
    "ASTROMETRY_VERIFIED": {"COMPLETE", "PARTIAL", "FAILED"},
}


@dataclass
class History:
    events: Events | None = None
    stages: list[dict] = field(default_factory=list)
    state: str = "PENDING"
    clock: float = field(default_factory=monotonic)

    def advance(self, state: str) -> None:
        if state not in TRANSITIONS.get(self.state, ()):
            raise ValueError(f"illegal state transition {self.state} -> {state}")
        now = monotonic()
        self.stages.append(
            {
                "state": state,
                "utc": datetime.now(UTC).isoformat(),
                "previous_stage_duration_s": now - self.clock,
            }
        )
        if self.events is not None:
            self.events.emit(
                "stage", stage=state, prior_stage=self.state, duration_s=now - self.clock
            )
        self.state, self.clock = state, now


def reduce_exposure(
    path: Path,
    config: Config,
    *,
    mode: str = "reduce",
    dark_id: str | None = None,
    flat_id: str | None = None,
    dry_run: bool = False,
    revision: str = "",
    memory_limit_mib: int | None = None,
    expected_input_sha256: str | None = None,
    job_id: str | None = None,
) -> dict:
    """Match, calibrate, assess and solve an exposure, retaining any science result."""
    if mode not in ("calibrate", "reduce"):
        raise ValueError("invalid processing mode")
    if job_id is not None:
        object_id(job_id)
    if expected_input_sha256 is not None:
        object_id(expected_input_sha256)
    events = (
        None
        if dry_run
        else Events(
            config.work_dir, "exposure", job_id=job_id, input_id=identity(str(path.resolve()))
        )
    )
    if events is not None:
        events.emit("started", mode=mode, expected_sha256=expected_input_sha256)
    try:
        result = _reduce(
            path,
            config,
            mode=mode,
            dark_id=dark_id,
            flat_id=flat_id,
            dry_run=dry_run,
            revision=revision,
            memory_limit_mib=memory_limit_mib,
            expected_input_sha256=expected_input_sha256,
            events=events,
        )
        if events is not None:
            events.emit(
                "reused" if result.get("reused") else "published", state=result.get("state")
            )
        return result
    except (Exception, KeyboardInterrupt) as exc:
        if events is not None:
            events.emit(
                "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                error_type=type(exc).__name__,
            )
        raise


def _reduce(
    path,
    config,
    *,
    mode,
    dark_id,
    flat_id,
    dry_run,
    revision,
    memory_limit_mib,
    expected_input_sha256,
    events,
):
    history = History(events=events)
    history.advance("VALIDATING")
    frame = inspect_frame(path, config)
    if events is not None:
        events.observation_id = frame.sha256
        events.emit("input_validated", shape=frame.shape)
    if expected_input_sha256 is not None and expected_input_sha256 != frame.sha256:
        raise FitsError("raw checksum changed after job creation")
    if frame.values["kind"] != "LIGHT":
        raise CalibrationError("science reduction requires a LIGHT exposure")
    role = reference_kind(config)
    dark = select_master(frame, config, role, dark_id)
    flat = select_master(frame, config, "FLAT", flat_id)
    verify_flat_lineage(flat, config)
    fd = flat.manifest["definition"]
    resolved = {
        "dark": {"id": dark.id, "sha256": dark.manifest["sha256"], "kind": role},
        "flat": {"id": flat.id, "sha256": flat.manifest["sha256"]},
        "flat_dark": {"id": fd["flat_dark"], "sha256": fd["flat_dark_sha256"]},
    }
    if events is not None:
        events.emit(
            "calibration_selected", master_ids={name: row["id"] for name, row in resolved.items()}
        )
    worker_config = (
        config
        if memory_limit_mib is None
        else Config.model_validate({**config.model_dump(), "memory_mib": memory_limit_mib})
    )
    cfg = config.model_dump(mode="json")
    external = astrometry.external_inputs(config.astrometry) if mode == "reduce" else {}
    expectation_sha = (
        digest(config.photon_expectation) if config.photon_expectation is not None else None
    )
    if expectation_sha is not None:
        external["photon_expectation"] = expectation_sha
    definition = {
        "input_sha256": frame.sha256,
        "data_origin": frame.origin,
        "masters": resolved,
        "config_hash": identity(cfg),
        "mode": mode,
        "revision": revision,
        "external": external,
        "software": versions(),
    }
    identifier = identity(definition)
    if events is not None:
        events.product_id = identifier
    target = config.work_dir / "products" / identifier
    product = target / "science.fits"
    if dry_run:
        return {"id": identifier, "path": str(product), **definition}
    if product.exists():
        status = validate_product(product)
        return {"id": identifier, "path": str(product), "reused": True, **status}
    with publish_directory(target) as temp:
        history.advance("CALIBRATING")
        image = apply_calibration(
            frame, dark, flat, worker_config, expectation_sha256=expectation_sha
        )
        history.advance("CALIBRATED")
        qc: dict = {"schema_version": 1, "status": "NOT_EVALUATED", "reasons": []}
        wcs_report: dict = {"schema_version": 1, "status": "NOT_EVALUATED", "reasons": []}
        accepted_wcs = None
        failures = []
        if mode == "reduce":
            history.advance("QC_RUNNING")
            try:
                qc, sources = measure(
                    image,
                    config.quality,
                    characterized(frame, config) and config.detector.saturation is not None,
                )
            except (ValueError, RuntimeError, FloatingPointError, MemoryError) as exc:
                failures.append({"stage": "qc", "type": type(exc).__name__, "reason": str(exc)})
                qc["reasons"] = [str(exc)]
                if events is not None:
                    events.emit("stage_failed", stage="QC", error_type=type(exc).__name__)
            else:
                history.advance("QC_COMPLETE")
                history.advance("ASTROMETRY_RUNNING")
                try:
                    pointing = None
                    if "RA" in frame.header and "DEC" in frame.header:
                        ra, dec = float(frame.header["RA"]), float(frame.header["DEC"])
                        if math.isfinite(ra) and math.isfinite(dec) and -90 <= dec <= 90:
                            pointing = (ra % 360, dec)
                    solution = astrometry.solve(
                        sources,
                        frame.shape,
                        Time(frame.midpoint, scale=frame.time_scale),
                        config.astrometry,
                        temp / "solver",
                        pointing,
                        online_root=config.work_dir / "astrometry-online",
                        image=image.science,
                    )
                    wcs_report = solution.report
                    fits.PrimaryHDU(header=solution.wcs.to_header(relax=True)).writeto(
                        temp / "solver" / "candidate.wcs", checksum=True
                    )
                    wcs_report["candidate_sha256"] = digest(temp / "solver" / "candidate.wcs")
                    if wcs_report["status"] == "VERIFIED":
                        accepted_wcs = solution.wcs
                        history.advance("ASTROMETRY_VERIFIED")
                        # Use a local two-axis geometric-mean scale for individual PSFs.
                        for candidate in qc["sources"]:
                            x, y = candidate["x"], candidate["y"]
                            origin = accepted_wcs.pixel_to_world(x, y)
                            sx = origin.separation(accepted_wcs.pixel_to_world(x + 1, y)).arcsec
                            sy = origin.separation(accepted_wcs.pixel_to_world(x, y + 1)).arcsec
                            candidate["fwhm_arcsec_approx"] = candidate["fwhm"] * math.sqrt(sx * sy)
                except (ValueError, OSError, RuntimeError) as exc:
                    failures.append(
                        {"stage": "astrometry", "type": type(exc).__name__, "reason": str(exc)}
                    )
                    wcs_report = {"schema_version": 1, "status": "FAILED", "reasons": [str(exc)]}
                    if category := getattr(exc, "category", None):
                        wcs_report["error_category"] = category
                        wcs_report["solve_status"] = (
                            "PENDING" if getattr(exc, "pending", False) else "FAILED"
                        )
                        if wcs_report["solve_status"] == "PENDING":
                            wcs_report["status"] = "UNVERIFIED"
                    accepted_wcs = None
                    if events is not None:
                        events.emit(
                            "stage_failed", stage="ASTROMETRY", error_type=type(exc).__name__
                        )
        if events is not None:
            events.emit(
                "scientific_status",
                qc=qc["status"],
                wcs=wcs_report["status"],
                uncertainty=image.noise_status,
            )
        complete = (
            accepted_wcs is not None
            and image.noise_status == "CONDITIONAL"
            and qc["status"] in ("PASS", "WARN", "FAIL")
        )
        history.advance("COMPLETE" if complete else "PARTIAL")
        write_json(temp / "qc.json", qc)
        write_json(temp / "astrometry.json", wcs_report)
        (temp / "quality.txt").write_text(
            "\n".join(
                [
                    f"Quality status  {qc['status']}",
                    f"WCS status  {wcs_report['status']}",
                    *(
                        f"{name}  {qc.get(name)}"
                        for name in (
                            "source_count",
                            "fwhm_px",
                            "ellipticity",
                            "background",
                            "background_rms",
                        )
                    ),
                    *qc["reasons"],
                    *wcs_report["reasons"],
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        write_science(
            temp / "science.fits",
            image,
            frame,
            config,
            definition,
            history.state,
            qc,
            wcs_report,
            accepted_wcs,
        )
        validate_product(temp / "science.fits", provenance=False)
        outputs = {
            p.relative_to(temp).as_posix(): digest(p) for p in temp.rglob("*") if p.is_file()
        }
        write_json(
            temp / "provenance.json",
            {
                "schema_version": 1,
                "id": identifier,
                "definition": definition,
                "config": cfg,
                "input": frame.manifest(),
                "state": history.state,
                "stages": history.stages,
                "failures": failures,
                "outputs": outputs,
                "algorithms": {
                    "calibration": "bias-flat-v1"
                    if role == "BIAS"
                    else "matched-dark-flat-dark-v1",
                    "noise": "independent-expectation-v1"
                    if expectation_sha
                    else "temporal-reference-plugin-v1",
                    "dq": "osp-dq-v1",
                    "quality": "gaussian-candidates-v1",
                    "astrometry": "astrometry-net-holdout-v1",
                },
                "assumptions": [
                    "flat scale treated as fixed",
                    "independent calibration samples",
                    "cross-pixel and cross-exposure covariance omitted",
                ],
            },
        )
    return {"id": identifier, "path": str(product), "reused": False, **validate_product(product)}
