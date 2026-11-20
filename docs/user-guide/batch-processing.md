# Batch processing and restart recovery

```sh
osp batch --input observations --config observatory.yaml
osp jobs list --config observatory.yaml
osp jobs inspect JOB_ID --config observatory.yaml --verify-products
osp jobs retry JOB_ID --config observatory.yaml
```

Replace JOB_ID with the batch result's ID. Batch discovery is recursive; each
exposure runs in an isolated subprocess with a bounded worker count and timeout.
SQLite checkpoints and an advisory single-job lock protect state. Repeating a
batch resumes pending/interrupted work; retry explicitly revisits failures.
Completed products are reused under the same definition.

Keep configuration, masters and external input files fixed while processing.
Changes produce a new processing identity. Use `--revision LABEL` for deliberate
reprocessing, including PARTIAL results whose external prerequisites are now
available. `--dark ID` and `--flat ID` select compatible references explicitly.
Do not reuse a synthetic workspace for observations.

Memory limits estimate algorithm arrays, not total process RSS. Leave headroom
for libraries and solver indexes. Events under work_dir/events record per-run
and job outcomes. See [recovery details](../installation/operations.md).
