# OSP a6 acceptance and release evidence

The committed baseline is a4 at `9ede8b6`. The initial working tree also
contained the a5 Nova/ANSVR implementation. This release is an engineering
alpha. The comparisons below apply to the recorded inputs and configuration.

Windows final suite: 56 passed, zero failed, one socket-based test skipped
after WinError 10013. Ruff lint/format, mypy and Twine checks passed. The
installed CLI generated a two-light sample and published two valid partial
products. The batch report verified both artifacts and recorded failed
astrometry as expected with the deliberately absent synthetic solver.

## Section 24 acceptance matrix

| Area | Status | Evidence and remaining limitations |
| --- | --- | --- |
| FITS ingestion | SOFTWARE_TESTED, REAL_DATA_VALIDATED for integrity | Integer scaling, BLANK, truncation, unsigned data, metadata and provenance checks. All 98 raw hashes matched the prior inventory. Supported raw image geometry is a single uncompressed 2D image. |
| Calibration | SYNTHETICALLY_VALIDATED | Seeded FITS, estimated masters, preserved negative values, matched dark and flat-dark, and separate short-exposure bias references. Astropy and independent scalar comparison. Real calibration is BLOCKED on missing darks and flats. |
| Uncertainty | SYNTHETICALLY_VALIDATED within model | Re-ran 180,000 draws per signal level and 240,000 covariance draws. Zero-signal plug-in bias persists; ERR remains conditional and omits full pixel and exposure covariance. |
| DQ masks | SOFTWARE_TESTED | Saturation uses characterized threshold, known defects have distinct bits, and optional isolated-impulse screening preserves SCI. Automated full detector defect characterization requires independent physical data. |
| QC | SYNTHETICALLY_VALIDATED | 18–20 fitted sources per standard field, median centroid error 0.030–0.035 px, FWHM 3.20–3.25 px. Crowded fits remain conservative and isolated-source quality does not establish photometric suitability. |
| Local astrometry | SOFTWARE_TESTED, live BLOCKED | ANSVR protocol fixtures pass. Local live probe returned WinError 10013. No live WCS or residual obtained. |
| Online astrometry | SOFTWARE_TESTED, live BLOCKED | Nova simulation covers credentials, polling, image authorization, timeouts, receipt reuse and fallback. Live authentication stopped at DNS before upload. |
| Gaia verification | SYNTHETICALLY_VALIDATED, real BLOCKED | Local ECSV cache, epoch/proper-motion checks, held-out matches, accepted and rejected WCS. No real residuals from a verified live solution. |
| Simulation | SYNTHETICALLY_VALIDATED | Seeded, checksummed FITS, bias/dark/flat/flat-dark, known signal, response, source catalogue and WCS. Adversarial inputs isolated from the ordinary batch. Large and interruption tests use the job runner. |
| Batch | SOFTWARE_TESTED, SYNTHETICALLY_VALIDATED | Per-frame workers, SQLite checkpoints, crash retry and receipt audits. See measured scaling below. No observing-night or live-queue throughput evidence. |
| Data integrity | REAL_DATA_VALIDATED for raw bytes, SOFTWARE_TESTED for publication | SHA-256, FITS checksums, atomic publication, output traversal checks, unchanged raw input. Power-loss durability remains unverified. |
| CLI | SOFTWARE_TESTED | Generation, master creation, reduction, product validation, batch and reports exercised from the installed wheel. |
| API | SOFTWARE_TESTED | Typed config and Python generation → masters → reduction → product-read integration tests. |
| Installation | SOFTWARE_TESTED | Fresh Windows venv with preinstalled dependencies. Independent dependency download in a clean environment is BLOCKED by restricted network. |
| Packaging | SOFTWARE_TESTED | Wheel, source distribution, Twine checks, source/member inspection and delivery checksums. |
| Windows | SOFTWARE_TESTED | Windows 11 build 26300 and Python 3.14.7. |
| Linux | BLOCKED | Hosted job not run. Workflow targets Linux and Windows with Python 3.11 and 3.14. |
| Documentation | SOFTWARE_TESTED within Windows workflow | Synthetic guide, API, model, CLI, operator capture and solver procedures. No independent Linux operator test. |
| Security | SOFTWARE_TESTED, dependency audit BLOCKED | Secret-free artifacts, bounded HTTP, explicit permission, FITS size admission, atomic output, checked relative paths. Local dependency consistency checked. Online dependency vulnerability resolution unavailable. |
| Open source | COMPLETE for private packaging | BSD-3-Clause, contributor docs, issue and PR templates, CI, source and wheel. Public hosting and published release require owner authorization. |
| Real instrument validation | BLOCKED | No matched darks or flat-darks in 98 files, clipped O flats, no validated MiniCam8 gain/read noise/linearity or repeated-field photometry. |

## Calibration and QC experiment

Run `python benchmarks/validate_simulation.py NEW_DIRECTORY` with the package
installed. The field has 20 injected sources and 12,288 pixels per exposure.
The comparison scales expected electrons by the median injected response and
divides by simulated gain. Three lights share the same masters.
Bias ranged from −0.077 to −0.007 ADU, pixel RMS from 6.69 to 6.79 ADU,
normalized residual SD from 1.013 to 1.017, and median aperture flux error
from −0.49% to −0.08%. One-sigma coverage was 67.8–68.4% and 1.96-sigma coverage
94.5–94.7%. The regression requires robust bias below 0.12 normalized units,
normalized SD between 0.88 and 1.16, and centroid median below 0.30 px.
Coverage values are descriptive because shared calibration correlates pixels
and exposures. This is not a standard-magnitude calibration.

Run `python benchmarks/commission_reference.py NEW_DIRECTORY` for an independent
Astropy CCDData comparison and separate scalar reference. For the measured
1,280 pixels, maximum science difference versus CCDData was 4.55e-13 ADU and
maximum one-sigma difference 1.95e-14 ADU. ccdproc is absent. The independent
arithmetic uses the same physical model and conditional-ERR assumptions.

Run `python benchmarks/uncertainty_commission.py` for low-count and covariance
results. At zero signal, mean predicted variance was 9.06% above truth
and the measured empirical variance was 0.93% above analytic truth.
One-ERR coverage was 70.92%, with Monte Carlo-only normal-approximation
95% interval 70.71–71.13%. Coverage at 1.96 ERR was 96.71%, with interval
96.63–96.80%. At 100 electrons the predicted-to-analytic variance ratio
was 0.99988. Cross-exposure covariance measured 2.027 e² versus 2.140 e²
first order. The tested acceptance requires variance scatter within 2%
and covariance differences below five Monte Carlo standard errors.
The low-signal plug-in estimator's positive bias is an explicit limitation.

See [detector calibration and noise assumptions](../science/assumptions-and-limitations.md),
[scientific references](../science/references.md), and the
[measurement checklist](../commissioning/FINAL-ACQUISITION.md).

## Operational boundaries

Measured on Windows, all samples were synthetic and all products were partial
because the solving executable was deliberately unavailable.

| Dimensions | Exposures | Workers | Runtime | Peak tree RSS | Resume |
| --- | ---: | ---: | ---: | ---: | ---: |
| 128 × 128 | 1 | 1 | 4.04 s | 245 MiB | 0.114 s |
| 128 × 128 | 10 | 2 | 17.86 s | 377 MiB | 0.157 s |
| 128 × 128 | 100 | 2 | 187.92 s | 377 MiB | 0.139 s |
| 128 × 128 | 200 | 2 | 376.22 s | 377 MiB | 0.106 s |
| 2180 × 3856 | 4 | 2 | 21.52 s | 1,426 MiB | 0.127 s |

The final full-resolution case wrote 606 MB of products. Sampled worker CPU
time was 36.25 s and sampled process I/O counters were 7.93 GB read and
606 MB written. These counters are not storage-device throughput.

`benchmarks/batch_commission.py` uses PSUtil sampling. Peak working-set sum
can double-count shared pages. CPU and process I/O are sampled lower bounds,
and Windows process I/O counters include cached or nonphysical operations.
Full-size solver latency and production observations remain unmeasured.
Use `--cases 1000:4` for an extended run. Verify power-loss recovery and
live solver load before unattended instrument use.
