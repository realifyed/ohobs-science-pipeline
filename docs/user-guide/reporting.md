# Reports and diagnostic plots

```sh
osp report --product PRODUCT --html exposure.html
osp report --latest --config observatory.yaml
osp report --job JOB_ID --config observatory.yaml --html batch.html
```

Replace PRODUCT/JOB_ID with returned values. Reports print JSON; --html writes
an additional standalone HTML summary. Product reports verify associated
evidence and expose state, integrity, quality and astrometry results. Batch
reports summarize persisted task outcomes. Inspect stage status independently
of command exit zero. Product and batch integrity failures cause nonzero exit.

For figures install `python -m pip install ".[diagnostics]"`, then:

```sh
osp plots --product PRODUCT --output diagnostics
```

Use a new output directory. Master plots additionally need --master ID and
--config; residual references must be independent and on the same grid and
units. See [diagnostics](../installation/operations.md). Reports can reveal
observation metadata and filesystem paths; review them before public sharing.
