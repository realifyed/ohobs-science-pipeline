"""Installable OSP command-line interface."""

import argparse
import json
import math
import platform
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
import yaml
from astropy.io import fits
from astropy.time import Time

from . import __version__, online_astrometry
from .astrometry import assess_candidate, probe_solver, solve, source_digest
from .characterization import characterize
from .config import BACKENDS, astrometry_override, load_config
from .diagnostics import readiness
from .dq import characterized, raw_mask
from .ingest import FitsError, inspect_frame
from .integrity import digest, read_json, versions, write_json
from .jobs import create_job, discover, job_info, run_job
from .masters import build_master, list_masters, load_master
from .pipeline import reduce_exposure
from .products import read_calibrated, validate_product
from .quality import measure
from .reduction import Calibrated
from .reporting import batch_report, exposure_report, write_html_report


def _config(args):
    config = load_config(args.config)
    return config.model_copy(
        update={
            "astrometry": astrometry_override(
                config.astrometry,
                getattr(args, "astrometry_backend", None),
                allow_online=getattr(args, "allow_online", False),
                allow_image=getattr(args, "allow_image_upload", False),
            )
        }
    )


def _masters(args):
    config = _config(args)
    if args.action == "build":
        paths = args.paths
        if not paths:
            directory = config.calibration_dir
            if directory is None or not directory.is_dir():
                raise ValueError("provide input paths or a calibration directory")
            paths = list(discover(directory))
        return build_master(paths, config, flat_dark_id=args.flat_dark, kind=args.kind).manifest
    if args.action == "list":
        return [
            {
                "id": m.id,
                "kind": m.manifest["definition"]["kind"],
                "statistics": m.manifest["statistics"],
            }
            for m in list_masters(config)
        ]
    return load_master(config, args.identifier).manifest


def _reduce(args):
    config = _config(args)
    worker_budget = args.memory_limit or config.memory_mib
    return reduce_exposure(
        args.input,
        config,
        mode=args.command,
        dark_id=args.dark,
        flat_id=args.flat,
        dry_run=args.dry_run,
        revision=args.revision,
        memory_limit_mib=worker_budget,
        expected_input_sha256=args.expected_input,
        job_id=args.job_id,
    )


def _stages(args):
    config = _config(args)
    if args.command == "astrometry":
        with fits.open(args.input, memmap=True, do_not_scale_image_data=True) as hdus:
            if "SCI" not in hdus or "OSPSCHM" not in hdus[0].header:
                return _solve_raw(args)
    calibrated = read_calibrated(args.input)
    header = fits.getheader(args.input)
    known = bool(header.get("SATKNOWN", False))
    report, sources = measure(calibrated, config.quality, known)
    if args.command == "qc":
        return report
    if args.output.exists():
        raise ValueError("astrometry diagnostics output already exists")
    time = Time(header["DATE-AVG"], scale=header["TIMESYS"].lower())
    result = solve(
        sources,
        calibrated.science.shape,
        time,
        config.astrometry,
        args.output,
        online_root=config.work_dir / "astrometry-online",
        image=calibrated.science,
    )
    _write_candidate(args.output, result)
    write_json(args.output / "validation.json", result.report)
    return result.report


def _raw_sources(path, config):
    frame = inspect_frame(path, config)
    if frame.values["kind"] != "LIGHT" or frame.midpoint is None:
        raise FitsError("raw astrometry diagnostic requires a LIGHT with an observation time")
    if frame.shape[0] * frame.shape[1] * 96 > config.memory_mib * 2**20:
        raise MemoryError("raw source extraction exceeds the configured memory estimate")
    with frame.image() as raw:
        data = raw.rows(0, frame.shape[0])
    mask = raw_mask(data, frame, config)
    image = Calibrated(data, np.broadcast_to(np.nan, data.shape), mask, "UNAVAILABLE")
    known = characterized(frame, config) and config.detector.saturation is not None
    qc, sources = measure(image, config.quality, known)
    return frame, data, qc, sources


def _write_candidate(output, result):
    candidate = output / "candidate.wcs"
    fits.PrimaryHDU(header=result.wcs.to_header(relax=True)).writeto(candidate, checksum=True)
    result.report["candidate_sha256"] = digest(candidate)


def _solve_raw(args):
    """Commission a solver on a raw light without publishing a science product."""
    config = _config(args)
    args.output.mkdir(parents=True, exist_ok=False)
    frame, data, qc, sources = _raw_sources(args.input, config)
    write_json(args.output / "sources.json", qc)
    report = {
        "schema_version": 1,
        "diagnostic": "RAW_LIGHT",
        "input_sha256": frame.sha256,
        "observation": frame.path.name,
        "midpoint": frame.midpoint,
        "source_count": len(sources),
        "extraction": config.quality.model_dump(mode="json"),
        "backend": config.astrometry.backend,
    }
    if getattr(args, "sources_only", False):
        report.update(status="EXTRACTED")
        write_json(args.output / "validation.json", report)
        return report
    try:
        time = Time(frame.midpoint, scale=frame.time_scale)
        pointing = None
        if "RA" in frame.header and "DEC" in frame.header:
            try:
                ra, dec = float(frame.header["RA"]), float(frame.header["DEC"])
                if math.isfinite(ra) and math.isfinite(dec) and -90 <= dec <= 90:
                    pointing = (ra % 360, dec)
            except (TypeError, ValueError):
                pass  # An optional malformed pointing hint does not block a blind solve.
        result = solve(
            sources,
            frame.shape,
            time,
            config.astrometry,
            args.output,
            pointing,
            online_root=config.work_dir / "astrometry-online",
            image=data,
        )
        _write_candidate(args.output, result)
        report.update(result.report)
    except (ValueError, OSError, RuntimeError) as exc:
        report.update(status="FAILED", reasons=[str(exc)])
        if isinstance(exc, online_astrometry.NovaError):
            report["error_category"] = exc.category
            if exc.pending:
                report.update(status="UNVERIFIED", solve_status="PENDING")
        write_json(args.output / "validation.json", report)
        raise
    write_json(args.output / "validation.json", report)
    return report


def _verify_wcs(args):
    config = _config(args)
    candidate = args.wcs or args.input
    with fits.open(args.input, memmap=True, do_not_scale_image_data=True) as hdus:
        calibrated = "SCI" in hdus and "OSPSCHM" in hdus[0].header
    if calibrated:
        image = read_calibrated(args.input)
        header = fits.getheader(args.input)
        _, sources = measure(image, config.quality, bool(header.get("SATKNOWN", False)))
        shape = image.science.shape
        time = Time(header["DATE-AVG"], scale=header["TIMESYS"].lower())
    else:
        frame, _, _, sources = _raw_sources(args.input, config)
        shape = frame.shape
        time = Time(frame.midpoint, scale=frame.time_scale)
    original = read_json(args.solve_report) if args.solve_report else {}
    independent = (
        original.get("independent_holdout") is True
        and original.get("candidate_sha256") == digest(candidate)
        and original.get("source_digest") == source_digest(sources)
    )
    settings = config.astrometry
    if original.get("backend", settings.backend) == "online":
        settings = settings.model_copy(
            update={
                "backend": "online",
                "catalogue_independence_evidence": settings.online.catalogue_independence_evidence,
            }
        )
    return assess_candidate(
        candidate, shape, sources[::3], time, settings, independent=independent
    ).report


def _online_status(args):
    config = _config(args)
    return online_astrometry.status(
        config.astrometry.online,
        config.work_dir / "astrometry-online",
        args.job_id,
        wait=args.wait,
        cancel=args.cancel,
        submission_id=args.attach,
        abandon=args.abandon,
    )


def _benchmark(args):
    start = perf_counter()
    count, pixels, total_bytes = 0, 0, 0
    for path in discover(args.dataset):
        frame = inspect_frame(path)
        count += 1
        pixels += frame.shape[0] * frame.shape[1]
        total_bytes += path.stat().st_size
    if count == 0:
        raise ValueError("no benchmark FITS inputs")
    elapsed = perf_counter() - start
    return {
        "stage": "ingest",
        "frames": count,
        "pixels": pixels,
        "bytes": total_bytes,
        "elapsed_s": elapsed,
        "frames_per_s": count / elapsed,
    }


def _doctor(args):
    result = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "dependencies": versions(),
        "checks": readiness(),
    }
    if args.config:
        config = _config(args)
        result["checks"] = readiness(config)
        result.update(
            node=config.node,
            work_dir=str(config.work_dir),
            astrometry_backend=config.astrometry.backend,
        )
        if args.probe:
            result["astrometry"] = probe_solver(config.astrometry)
    elif args.probe:
        raise ValueError("--probe requires --config")
    return result


def _report(args):
    if args.product:
        report = exposure_report(args.product)
    else:
        if args.config is None:
            raise ValueError("--job and --latest require --config")
        work = _config(args).work_dir
        if args.latest:
            candidates = list((work / "products").glob("*/science.fits"))
            if not candidates:
                raise ValueError("no published products found")
            report = exposure_report(
                max(candidates, key=lambda p: (p.stat().st_mtime_ns, p.parent.name))
            )
        else:
            report = batch_report(work, args.job)
    if args.html:
        write_html_report(args.html, report)
    return report


def _plots(args):
    from .plots import generate

    if args.master and not args.config:
        raise ValueError("--master requires --config")
    if args.reference and not args.product:
        raise ValueError("--reference requires --product")
    return {
        "files": generate(
            args.output,
            report=exposure_report(args.product) if args.product else None,
            master=load_master(_config(args), args.master) if args.master else None,
            reference=args.reference,
            uncertainty=args.uncertainty,
            benchmark=args.benchmark,
        )
    }


def _gaia_fetch(args):
    from .astrometry import load_candidate
    from .gaia import reference

    config = _config(args)
    settings = config.astrometry.gaia
    shape = (args.height, args.width)
    wcs = load_candidate(fits.getheader(args.wcs), shape, config.astrometry)
    path, details = reference(
        wcs,
        shape,
        Time(args.midpoint, scale="utc"),
        settings,
        settings.cache_dir or config.work_dir / "gaia-cache",
    )
    return {"path": str(path), **details}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="osp", description="OHOBS Science Pipeline")
    commands = p.add_subparsers(dest="command", required=True)

    def configured(parser, optional=False):
        parser.add_argument("--config", type=Path, required=not optional)
        return parser

    def backend_options(command, *, stage=False):
        flag = "--backend" if stage else "--astrometry-backend"
        command.add_argument(flag, dest="astrometry_backend", choices=BACKENDS)
        command.add_argument(
            "--allow-online", action="store_true", help="authorize this run's Nova submission"
        )
        command.add_argument(
            "--allow-image-upload",
            action="store_true",
            help="also authorize image pixels when configured",
        )
        return command

    commands.add_parser("version").set_defaults(run=lambda a: {"version": __version__})
    doctor = configured(
        commands.add_parser("doctor", help="report the runtime environment"), optional=True
    )
    doctor.add_argument(
        "--probe", action="store_true", help="also probe the configured astrometry backend"
    )
    doctor.add_argument("--backend", dest="astrometry_backend", choices=BACKENDS)
    doctor.set_defaults(run=_doctor)
    cfg = commands.add_parser("config").add_subparsers(dest="action", required=True)
    configured(cfg.add_parser("validate")).set_defaults(
        run=lambda a: _config(a).model_dump(mode="json")
    )
    ing = commands.add_parser("fits").add_subparsers(dest="action", required=True)
    ins = configured(ing.add_parser("inspect"), optional=True)
    ins.add_argument("input", type=Path)
    ins.set_defaults(
        run=lambda a: inspect_frame(a.input, _config(a) if a.config else None).manifest()
    )
    camera = commands.add_parser("camera").add_subparsers(dest="action", required=True)
    detect = configured(camera.add_parser("characterize"))
    detect.add_argument("sequence", type=Path, help="JSON illumination and dark pair manifest")
    detect.set_defaults(
        run=lambda a: characterize(json.loads(a.sequence.read_text(encoding="utf-8")), _config(a))
    )
    masters = commands.add_parser("masters").add_subparsers(dest="action", required=True)
    build = configured(masters.add_parser("build"))
    build.add_argument("paths", nargs="*", type=Path)
    build.add_argument("--kind", choices=["BIAS", "DARK", "FLAT_DARK", "FLAT"])
    build.add_argument("--flat-dark")
    build.add_argument(
        "--bias-reference", dest="flat_dark", help="flat offset reference for bias-only calibration"
    )
    build.set_defaults(run=_masters)
    configured(masters.add_parser("list")).set_defaults(run=_masters)
    mi = configured(masters.add_parser("inspect"))
    mi.add_argument("identifier")
    mi.set_defaults(run=_masters)
    for name in ("reduce", "calibrate"):
        stage = configured(commands.add_parser(name))
        if name == "reduce":
            backend_options(stage)
        stage.add_argument("input", type=Path)
        stage.add_argument("--dark")
        stage.add_argument(
            "--bias", dest="dark", help="science offset reference for bias-only calibration"
        )
        stage.add_argument("--flat")
        stage.add_argument("--dry-run", action="store_true")
        stage.add_argument("--revision", default="", help="deliberate reprocessing identifier")
        stage.add_argument("--memory-limit", type=int, help=argparse.SUPPRESS)
        stage.add_argument("--expected-input", help=argparse.SUPPRESS)
        stage.add_argument("--job-id", help=argparse.SUPPRESS)
        stage.set_defaults(run=_reduce)
    qc = configured(commands.add_parser("qc"))
    qc.add_argument("input", type=Path)
    qc.set_defaults(run=_stages)
    groups = commands.add_parser("astrometry").add_subparsers(dest="action", required=True)
    probe = configured(groups.add_parser("probe", help="check the selected solver connection"))
    probe.add_argument("--backend", dest="astrometry_backend", choices=BACKENDS)
    probe.set_defaults(run=lambda a: probe_solver(_config(a).astrometry))
    astro = backend_options(configured(groups.add_parser("solve")), stage=True)
    astro.add_argument("input", type=Path)
    astro.add_argument("--output", required=True, type=Path)
    astro.add_argument(
        "--verify", action="store_true", help="require verified WCS for a successful exit status"
    )
    astro.set_defaults(run=_stages)
    diagnostic = backend_options(
        configured(
            groups.add_parser(
                "diagnose-raw", help="diagnostic WCS on a raw light without calibration"
            )
        ),
        stage=True,
    )
    diagnostic.add_argument("input", type=Path)
    diagnostic.add_argument("--output", required=True, type=Path)
    diagnostic.add_argument(
        "--sources-only", action="store_true", help="rank a field without solving"
    )
    diagnostic.set_defaults(run=_solve_raw)
    status = configured(groups.add_parser("status", help="inspect or resume a Nova job"))
    status.add_argument("job_id", help="Nova job number or OSP receipt ID")
    action = status.add_mutually_exclusive_group()
    action.add_argument("--wait", action="store_true", help="resume polling a saved receipt")
    action.add_argument("--cancel", action="store_true", help="cancel the local wait only")
    action.add_argument(
        "--attach",
        metavar="SUBMISSION_ID",
        help="attach a known Nova submission to an ambiguous receipt",
    )
    action.add_argument(
        "--abandon",
        action="store_true",
        help="retire an ambiguous receipt after checking Nova history",
    )
    status.set_defaults(run=_online_status)
    verification = configured(
        groups.add_parser(
            "verify", help="check a WCS against the configured reference without uploading"
        )
    )
    verification.add_argument("input", type=Path)
    verification.add_argument("--wcs", type=Path)
    verification.add_argument(
        "--solve-report",
        type=Path,
        help="solve report binding the candidate to its held-out source set",
    )
    verification.set_defaults(run=_verify_wcs, verify=True)
    valid = commands.add_parser("validate")
    valid.add_argument("input", type=Path)
    valid.set_defaults(run=lambda a: validate_product(a.input))
    batch = backend_options(configured(commands.add_parser("batch")))
    batch.add_argument("directory", nargs="?", type=Path)
    batch.add_argument("--input", type=Path)
    batch.add_argument("--dark")
    batch.add_argument("--flat")
    batch.add_argument("--revision", default="")
    batch.add_argument("--dry-run", action="store_true")
    batch.set_defaults(
        run=lambda a: create_job(
            a.input or a.directory or _config(a).raw_dir or Path(),
            a.config,
            a.dark,
            a.flat,
            a.revision,
            a.dry_run,
            astrometry_backend=a.astrometry_backend,
            allow_online=a.allow_online,
            allow_image_upload=a.allow_image_upload,
        )
    )
    jobs = commands.add_parser("jobs").add_subparsers(dest="action", required=True)
    for action in ("list", "inspect", "retry"):
        job = configured(jobs.add_parser(action))
        if action != "list":
            job.add_argument("id")
        if action == "inspect":
            job.add_argument("--verify-products", action="store_true")
        job.set_defaults(
            run=lambda a: (
                run_job(_config(a).work_dir, a.id, retry=True)
                if a.action == "retry"
                else job_info(
                    _config(a).work_dir,
                    getattr(a, "id", None),
                    verify_products=getattr(a, "verify_products", False),
                )
            )
        )
    bench = commands.add_parser("benchmark")
    bench.add_argument("--dataset", type=Path, required=True)
    bench.set_defaults(run=_benchmark)
    report = configured(
        commands.add_parser("report", help="inspect calibrated evidence and batch outcomes"),
        optional=True,
    )
    target = report.add_mutually_exclusive_group(required=True)
    target.add_argument("--product", type=Path)
    target.add_argument("--job")
    target.add_argument("--latest", action="store_true")
    report.add_argument("--html", type=Path, help="write an additional standalone HTML report")
    report.set_defaults(run=_report)
    plots = configured(
        commands.add_parser("plots", help="render measured diagnostics"), optional=True
    )
    plots.add_argument("--output", required=True, type=Path)
    plots.add_argument("--product", type=Path)
    plots.add_argument(
        "--reference", type=Path, help="same-grid, same-unit independent residual reference"
    )
    plots.add_argument("--master", help="calibration master identifier")
    plots.add_argument("--uncertainty", type=Path, help="Monte Carlo JSON")
    plots.add_argument("--benchmark", type=Path, help="benchmark JSON Lines")
    plots.set_defaults(run=_plots)
    gaia = configured(commands.add_parser("gaia-fetch", help="cache Gaia for a candidate WCS"))
    gaia.add_argument("--wcs", required=True, type=Path)
    gaia.add_argument("--height", required=True, type=int)
    gaia.add_argument("--width", required=True, type=int)
    gaia.add_argument("--midpoint", required=True, help="UTC observation midpoint")
    gaia.set_defaults(run=_gaia_fetch)
    return p


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    command_parser = parser()
    if arguments[:1] == ["simulate"]:
        command_parser.error("install ohobs-science-sim and use osp-sim generate")
    args = command_parser.parse_args(arguments)
    try:
        result = args.run(args)
        print(json.dumps(result, indent=2, allow_nan=False, default=str))
        if getattr(args, "verify", False) and result["status"] != "VERIFIED":
            return 1
        if isinstance(result, dict) and any(
            result.get("counts", {}).get(k) for k in ("FAILED", "QUARANTINED")
        ):
            return 1
        if isinstance(result, dict) and result.get("product_integrity", {}).get("FAILED"):
            return 1
        return 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        MemoryError,
        KeyError,
        fits.VerifyError,
        yaml.YAMLError,
    ) as exc:
        print(
            json.dumps(
                {
                    "state": "QUARANTINED"
                    if isinstance(exc, FitsError)
                    else "PENDING"
                    if getattr(exc, "pending", False)
                    else "FAILED",
                    "stage": args.command,
                    "type": type(exc).__name__,
                    "reason": "Invalid YAML configuration"
                    if isinstance(exc, yaml.YAMLError)
                    else str(exc),
                    **(
                        {"error_category": exc.category}
                        if isinstance(exc, online_astrometry.NovaError)
                        else {}
                    ),
                    "version": __version__,
                }
            ),
            file=sys.stderr,
        )
        return 1
