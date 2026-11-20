# CLI reference

All examples below use an existing OSP YAML file called CONFIG.

| Task | Command |
| --- | --- |
| Inspect installed environment | `osp doctor` |
| Generate reproducible test data using the optional toolkit | `osp-sim generate --profile standard --seed 1234 --output example --adversarial` |
| Verify and report an exposure | `osp report --product PRODUCT --html exposure.html` |
| Verify and summarize a batch | `osp report --job JOB_ID --config CONFIG --html batch.html` |
| Plot scientific diagnostics | `osp plots --product PRODUCT --master ID --config CONFIG --output plots` |
| Cache a Gaia catalogue for a known WCS | `osp gaia-fetch --wcs WCS.fits --height H --width W --midpoint DATE --config CONFIG` |
| Authenticate to Nova without uploading | `osp doctor --config CONFIG --backend online --probe` |
| Test local ANSVR | `osp astrometry probe --config CONFIG --backend local` |
| Solve a raw light or calibrated product locally | `osp astrometry solve observation.fits --config CONFIG --backend local --output local-result` |
| Authorize a Nova centroid solve | `osp astrometry solve observation.fits --config CONFIG --backend online --allow-online --output nova-result` |
| Local-first solve with authorized fallback | `osp astrometry solve observation.fits --config CONFIG --backend auto --allow-online --output auto-result` |
| Inspect a Nova job or an OSP receipt | `osp astrometry status ID --config CONFIG` |
| Resume OSP polling | `osp astrometry status RECEIPT_ID --config CONFIG --wait` |
| Verify a candidate against Gaia | `osp astrometry verify observation.fits --wcs nova-result/candidate.wcs --solve-report nova-result/validation.json --config CONFIG` |
| Apply backend and permission to reduction | `osp reduce observation.fits --config CONFIG --astrometry-backend online --allow-online` |
| Queue a local-first batch | `osp batch --input observations --config CONFIG --astrometry-backend auto --allow-online` |

AUTO also requires `astrometry.fallback_enabled: true` before taking the
online branch. Image upload requires its separate flag or config permission.
Use `--verify` on `astrometry solve` to require scientific verification
for a successful exit status. Diagnostic JSON reports `solve_status` and
verification `status` separately. The receipt is independent of the
diagnostic output directory. See the [configuration reference](configuration.md).
