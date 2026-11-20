# Architecture and operations

Public Python entry points include `ingest.inspect_frame`, `masters.build_master`, `masters.select_master`, `reduction.apply_calibration`, `quality.measure`, `astrometry.solve`, `products.validate_product`, and `pipeline.reduce_exposure`. Config-relative paths resolve from the YAML. Explicit master IDs take precedence over registry selection. Metadata overrides take precedence over header aliases and retain observed values in provenance. Full-frame ROI origin can be inferred only with matching configured geometry at 1×1 binning. Require additional settings or optical identifiers using header-key lists.

One uncompressed 2D science HDU is supported. Keep files still being acquired or transferred in a staging location. OSP checks HDU lengths, available FITS checksums, SHA-256 and ordinary file changes during processing. Raw files open read-only. Calibrators use row tiles and disk-backed staging. The memory budget is an admission estimate for algorithm arrays. Python, native libraries, mapping caches, subprocesses and solver indexes consume additional resources.

Batch workers process one exposure per isolated subprocess, with SQLite checkpoints and a single-job lock. Repeating a batch resumes pending or interrupted frames. `osp jobs retry JOB_ID --config CONFIG` retries failed frames. A changed registry or configuration requires a new job. Use a new revision to redo a PARTIAL result. Abrupt termination may leave an unpublished dot-prefixed temporary directory. Remove it after confirming related workers have stopped. Keep raw data, manifests and exact masters for reproducibility.

COMPLETE requires evaluated QC, conditional uncertainty and verified WCS. A QC FAIL may coexist with COMPLETE. PARTIAL retains calibrated arrays when stages are unavailable or fail. QUARANTINED denotes a FITS ingestion failure, while FAILED indicates a selection, resource or write problem. An unverified candidate WCS remains a diagnostic.

Export a field-sized Gaia DR3 reference ECSV with `source_id, ra, dec, pmra, pmdec, ref_epoch` and optionally `ruwe, duplicated_source`. Units are degrees, mas/year and TCB Julian years. Record the catalogue query, selection and solver index provenance alongside the run configuration. Set scientifically appropriate scale and RMS bounds. The local adapter needs Astrometry.net and its index files installed on its host.

`osp astrometry probe` reports whether the solver launches. `osp astrometry
diagnose-raw` tests extraction and the solver before the matching masters are
available. Its reports are diagnostic only. `osp astrometry solve --verify`
returns a failing exit status if the reference check does not verify the
candidate. See [ANSVR Windows commissioning](commissioning/ANSVR-WINDOWS.md).
Changes to the recorded solver files, catalogue or index manifest produce a
different batch identity. Keep those files and the registry fixed while workers
are running.

`osp doctor --config CONFIG` records the installed software and selected
backend. Add `--probe` to require a live solver probe. Use
`osp jobs inspect JOB_ID --config CONFIG --verify-products` to recheck
committed FITS and provenance against a job receipt. This check does not
modify the batch database or repair a product. Reprocess at a new revision
after investigating a damaged product.

`osp benchmark --dataset PATH` times ingestion. The synthetic benchmark additionally times all three master builds, calibration and QC.

## Distribution

OSP uses BSD-3-Clause. The installed dependency metadata identifies NumPy and SciPy as BSD, Astropy as BSD-3-Clause, and Pydantic and PyYAML as MIT. Astrometry.net is installed separately and invoked as a local executable. The source distribution excludes OHOBS observations and private configuration.
