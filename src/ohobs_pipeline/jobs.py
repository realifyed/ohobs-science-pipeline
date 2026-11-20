"""SQLite job checkpoints and bounded, isolated per-exposure workers."""

import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import closing
from pathlib import Path
from time import perf_counter

from astropy.io import fits

from .astrometry import external_inputs
from .config import astrometry_override, load_config
from .events import Events
from .ingest import file_signature, open_fits
from .integrity import digest, identity, object_id, versions
from .origin import Origin, OriginError, classify_origin, require_workflow
from .products import validate_product

EXTENSIONS = {".fits", ".fit", ".fts"}


def discover(path: Path):
    """Yield matching FITS paths without following directory symlinks."""
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for name in sorted(files):
            file = Path(root) / name
            if file.suffix.lower() in EXTENSIONS and not file.is_symlink():
                yield file.resolve()


def connect(work: Path) -> sqlite3.Connection:
    work.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(work / "jobs.sqlite3", timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS job (
          id TEXT PRIMARY KEY, config TEXT NOT NULL, config_digest TEXT NOT NULL,
          source TEXT NOT NULL, definition TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task (
          job TEXT, path TEXT, checksum TEXT, state TEXT, outcome TEXT,
          PRIMARY KEY (job, path)
        );
    """)
    return db


def _registry_fingerprint(work: Path) -> str:
    manifests = (work / "masters").glob("*/manifest.json")
    return identity(
        sorted((p.parent.name, digest(p)) for p in manifests if not p.parent.name.startswith("."))
    )


def create_job(
    source: Path,
    config_path: Path,
    dark: str | None = None,
    flat: str | None = None,
    revision: str = "",
    dry_run: bool = False,
    *,
    astrometry_backend: str | None = None,
    allow_online: bool = False,
    allow_image_upload: bool = False,
) -> dict:
    config_path = config_path.resolve(strict=True)
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError("batch input must be a directory")
    config = load_config(config_path)
    overrides = {
        "backend": astrometry_backend,
        "allow_online": allow_online,
        "allow_image": allow_image_upload,
    }
    config = config.model_copy(
        update={
            "astrometry": astrometry_override(
                config.astrometry,
                astrometry_backend,
                allow_online=allow_online,
                allow_image=allow_image_upload,
            )
        }
    )
    if config.work_dir.resolve().is_relative_to(source):
        raise ValueError("work directory must be outside batch input")
    # Preflight origin without loading pixel data. Malformed FITS remain isolated by the worker.
    snapshot = []
    origins: set[Origin] = set()
    for path in discover(source):
        before = file_signature(path)
        size = before[2]
        if 0 < size <= config.max_input_mib * 2**20 and size % 2880 == 0:
            try:
                with open_fits(path) as hdus:
                    origins.add(classify_origin(*(h.header for h in hdus)))
            except OriginError:
                raise
            except (OSError, ValueError, fits.VerifyError):
                pass
        snapshot.append((str(path), digest(path)))
        if file_signature(path) != before:
            raise OriginError("batch input changed during origin preflight")
    if not snapshot:
        raise ValueError("no FITS inputs")
    if len(origins) > 1:
        raise OriginError("batch contains mixed data origins or simulator identities")
    for origin in origins:
        require_workflow(origin, config.synthetic_test)
    config_hash = digest(config_path)
    definition = {
        "input": snapshot,
        "config": config.model_dump(mode="json"),
        "dark": dark,
        "flat": flat,
        "registry": _registry_fingerprint(config.work_dir),
        "astrometry_inputs": external_inputs(config.astrometry),
        "astrometry_overrides": overrides,
        "software": versions(),
        "revision": revision,
    }
    job = identity(definition)
    if dry_run:
        return {"id": job, "count": len(snapshot), "status": "DRY_RUN"}
    with closing(connect(config.work_dir)) as db, db:
        db.execute(
            "INSERT OR IGNORE INTO job VALUES (?,?,?,?,?)",
            (job, str(config_path), config_hash, str(source), json.dumps(definition)),
        )
        db.executemany(
            "INSERT OR IGNORE INTO task VALUES (?,?,?,'PENDING',NULL)",
            ((job, path, checksum) for path, checksum in snapshot),
        )
    return run_job(config.work_dir, job)


def _run_worker(
    path: str, expected: str, config_path: str, timeout: int, memory_mib: int, definition: dict
) -> tuple[str, dict]:
    started = perf_counter()
    try:
        args = [
            sys.executable,
            "-m",
            "ohobs_pipeline",
            "reduce",
            path,
            "--config",
            config_path,
            "--memory-limit",
            str(memory_mib),
            "--revision",
            definition["revision"],
            "--expected-input",
            expected,
        ]
        for key in ("dark", "flat"):
            if definition[key]:
                args.extend(("--" + key, definition[key]))
        if definition.get("job_id"):
            args.extend(("--job-id", definition["job_id"]))
        overrides = definition.get("astrometry_overrides", {})
        if overrides.get("backend"):
            args.extend(("--astrometry-backend", overrides["backend"]))
        if overrides.get("allow_online"):
            args.append("--allow-online")
        if overrides.get("allow_image"):
            args.append("--allow-image-upload")
        env = {
            **os.environ,
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            report = json.loads(proc.stdout)
        else:
            lines = proc.stderr.strip().splitlines()
            try:
                report = json.loads(lines[-1]) if lines else {}
            except ValueError:
                report = {}
            report.update({"returncode": proc.returncode, "stderr_tail": proc.stderr[-4000:]})
        report["duration_s"] = perf_counter() - started
        return report.get("state", "FAILED"), report
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return "FAILED", {
            "error": str(exc),
            "kind": type(exc).__name__,
            "duration_s": perf_counter() - started,
        }


def run_job(work: Path, job: str, *, retry: bool = False) -> dict:
    job = object_id(job)
    with closing(connect(work)) as db:
        row = db.execute(
            "SELECT config, config_digest, definition FROM job WHERE id=?", (job,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown job {job}")
        config_path, expected, definition_json = row
        if digest(Path(config_path)) != expected:
            raise ValueError("job configuration changed; create a new job")
        config = load_config(Path(config_path))
        definition = json.loads(definition_json)
        config = config.model_copy(
            update={
                "astrometry": astrometry_override(
                    config.astrometry, **definition.get("astrometry_overrides", {})
                )
            }
        )
        if (
            _registry_fingerprint(work) != definition["registry"]
            or versions() != definition["software"]
        ):
            raise ValueError("job master registry or software changed; create a new job")
        if external_inputs(config.astrometry) != definition.get("astrometry_inputs"):
            raise ValueError("job astrometry inputs changed; create a new job")
        worker_budget = config.memory_mib // config.workers
        if worker_budget < 16:
            raise ValueError("per-worker memory budget must be at least 16 MiB")
        # A database write transaction guards the reset and worker claims. An
        # OS-held file lock spanning execution allows recovery after process death.
        from .job_lock import job_lock

        with job_lock(work / (job + ".lock")):
            events = Events(work, "batch", job_id=job)
            events.emit("batch_started", workers=config.workers, retry=retry)
            with db:
                recovered = db.execute(
                    "UPDATE task SET state='PENDING' WHERE job=? AND state='VALIDATING'", (job,)
                ).rowcount
                retries = 0
                if retry:
                    retries = db.execute(
                        "UPDATE task SET state='PENDING' WHERE job=? AND state='FAILED'", (job,)
                    ).rowcount
            events.emit("checkpoint_recovery", interrupted=recovered, retry_queued=retries)
            worker_definition = {**definition, "job_id": job}
            with ThreadPoolExecutor(max_workers=config.workers) as pool:
                active: dict[Future[tuple[str, dict]], tuple[str, str]] = {}
                while True:
                    with db:
                        rows = db.execute(
                            "SELECT path, checksum FROM task WHERE job=? AND "
                            "state='PENDING' ORDER BY path LIMIT ?",
                            (job, config.workers - len(active)),
                        ).fetchall()
                        db.executemany(
                            "UPDATE task SET state='VALIDATING' WHERE job=? AND path=?",
                            ((job, path) for path, _ in rows),
                        )
                    for path, checksum in rows:
                        events.emit("frame_dispatched", frame_sha256=checksum)
                        future = pool.submit(
                            _run_worker,
                            path,
                            checksum,
                            config_path,
                            config.worker_timeout_s,
                            worker_budget,
                            worker_definition,
                        )
                        active[future] = (path, checksum)
                    if not active:
                        break
                    ready, _ = wait(active, return_when=FIRST_COMPLETED)
                    with db:
                        for future in ready:
                            state, report = future.result()
                            report["job"] = job
                            path, checksum = active.pop(future)
                            db.execute(
                                "UPDATE task SET state=?,outcome=? WHERE job=? AND path=?",
                                (state, json.dumps(report), job, path),
                            )
                            events.emit(
                                "frame_result",
                                frame_sha256=checksum,
                                state=state,
                                duration_s=report.get("duration_s"),
                                exit_code=report.get("returncode"),
                                product_id=report.get("id"),
                            )
            result = job_info(work, job)
            events.emit("batch_finished", counts=result["counts"])
            return result


def job_info(work: Path, job: str | None = None, *, verify_products: bool = False) -> dict:
    with closing(connect(work)) as db:
        if job is None:
            return {
                "jobs": [
                    {"id": identifier, "source": source}
                    for identifier, source in db.execute("SELECT id,source FROM job")
                ]
            }
        job = object_id(job)
        records = [
            {"path": path, "state": state, "outcome": json.loads(outcome) if outcome else None}
            for path, state, outcome in db.execute(
                "SELECT path,state,outcome FROM task WHERE job=? ORDER BY path", (job,)
            )
        ]
        if not records:
            raise ValueError(f"unknown job {job}")
        result = {
            "id": job,
            "counts": {
                state: sum(t["state"] == state for t in records)
                for state in sorted({t["state"] for t in records})
            },
            "frames": records,
        }
        if verify_products:
            outcome_counts = {"VERIFIED": 0, "FAILED": 0}
            for record in records:
                if record["state"] not in {"PARTIAL", "COMPLETE"}:
                    continue
                try:
                    outcome = record["outcome"]
                    identifier = object_id(outcome["id"])
                    product = (work / "products" / identifier / "science.fits").resolve()
                    if not product.is_relative_to((work / "products").resolve()):
                        raise ValueError("product path resolves outside the work registry")
                    verified = validate_product(product)
                    if verified["state"] != record["state"]:
                        raise ValueError("product state differs from the job receipt")
                except (
                    OSError,
                    ValueError,
                    TypeError,
                    KeyError,
                    RuntimeError,
                    fits.VerifyError,
                ) as exc:
                    record["product_integrity"] = {"status": "FAILED", "reason": str(exc)}
                    outcome_counts["FAILED"] += 1
                else:
                    record["product_integrity"] = {"status": "VERIFIED"}
                    outcome_counts["VERIFIED"] += 1
            result["product_integrity"] = outcome_counts
        return result
