# OSP 0.1.0a4 readiness

See [a5 dual-backend readiness](../validation/dual-backend-a5.md) for the
subsequent Nova and AUTO work.

Decision: publishable as an engineering alpha in the commissioning kit.
The release-candidate gate remains **BLOCKED** while live ANSVR operation,
independent astrometry, real calibration and hosted coverage remain open.

| Gate | Classification | Evidence or remaining blocker |
| --- | --- | --- |
| ANSVR HTTP integration | IMPLEMENTED, SYNTHETICALLY VALIDATED | Contract tests exercise login, multipart centroid upload, pending and completed submissions, failed job, FITS candidate download, and fit/holdout separation. |
| HTTP reachability and real solve | FAILED in development, BLOCKED on the observatory host | Port 8080 was confirmed from the installed service and historical logs. WinError 10013 prevented access in the development session. The ordinary observing-account run is pending. |
| Selection of an O field | REAL-DATA VALIDATED for candidate extraction | 49 fitted candidates in the selected O exposure after screening seven real lights. |
| Real Gaia validation | BLOCKED | Requires a valid real WCS and a covering Gaia ECSV. Synthetic tests cover the epoch and WCS mathematics. |
| Ingestion and raw integrity | REAL-DATA VALIDATED | 98 real FITS source checksums agree with the previous inventory. |
| OHOBS detector calibration and photometry | BLOCKED | No compatible darks or flat-darks. Node 01 gain, read noise, linearity and covariance still require physical measurements and withheld observations. |
| Marginal uncertainty and common calibration errors | SYNTHETICALLY VALIDATED within the specified model | Independent Poisson/Gaussian trials confirm the generating variance and quantify low-count plug-in bias and correlations. Real uncertainty interval coverage is BLOCKED. |
| FITS publication, checkpoint recovery and receipt revalidation | SYNTHETICALLY VALIDATED | Tests exercise interrupted workers, retry, immutable products, semantic FITS validation, and detection of a missing product during a read-only audit. |
| Full-resolution batch capacity | SYNTHETICALLY VALIDATED | One- and two-worker runs produced valid partial receipts. Production-length acquisition, solver throughput and power-loss behavior remain BLOCKED. |
| Local installation, CLI and package checks | SYNTHETICALLY VALIDATED | Windows Python 3.14 package build, wheel smoke test and local tests. |
| Hosted Windows and Linux matrix | IMPLEMENTED, BLOCKED | CI includes installation and an installed-wheel synthetic smoke test. This workspace has no configured upstream remote, and GitHub authentication and network checks failed. |
| Full production operation | BLOCKED | There is no completed production observing-night trial with the live solver and measured calibrations. |

## Full-detector benchmark

Windows 11 build 26300, 12 logical AMD64 CPUs, Python 3.14.7, NumPy 2.3.4,
SciPy 1.18.1 and Astropy 7.2.0. The aggregate configured frame budget was
4 GiB. Each trial used a fresh synthetic library with five inputs per master.
Wall times start after raw and master generation. Process-tree working set is
sampled every 50 ms and can double-count shared pages.

| 2180 × 3856 exposures | Workers | Wall time | Tree peak | Resume | Products |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 1 | 14.71 s | 797.5 MiB | 0.094 s | 2 PARTIAL |
| 4 | 2 | 17.59 s | 1387.1 MiB | 0.106 s | 4 PARTIAL |

Rerun with `python benchmarks/batch_commission.py --shape 2180 3856 --cases 2:1 4:2`
using the optional psutil dependency. Audit published results with
`osp jobs inspect JOB_ID --config CONFIG --verify-products`. Inspection is
read-only and returns a failing exit status for damaged or missing products.
Preserve defective output for diagnosis and use a new revision when
reprocessing. Keep raw data and master identity fixed.

See the [ANSVR validation report](ANSVR-HTTP-VALIDATION.md),
[acquisition checklist](FINAL-ACQUISITION.md), and
[uncertainty validation](../validation/uncertainty-commissioning-a4.md).
