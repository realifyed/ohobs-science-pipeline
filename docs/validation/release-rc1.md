# OSP 0.1.0rc1 software completion evidence

This is a private software release candidate built from the a6 working tree.
The last committed baseline was a4. Real astronomical astrometry, real detector
commissioning and observing-night operations require separate acceptance.

## Latest assignment

| Requirement | Status | Evidence and remaining gates |
| --- | --- | --- |
| Automated Gaia | SYNTHETICALLY VALIDATED; live BLOCKED | The automatic TAP path, immutable cache, RA wrap, epoch propagation, spatial residuals and offline failure were tested with a known WCS and catalogue fixtures. ESA access failed at DNS before TAP replied. Run the live script on a host that can reach the archive. |
| Scientific diagnostics | SOFTWARE TESTED | Diagnostic PNGs are derived from product pixels, QC measurements, reference residuals, instrument masters and measured benchmark files. An independent reference on the same grid and with the same BUNIT is required for calibration residuals. Astrometric plots need measured matches. |
| Structured logging | SOFTWARE TESTED | Exposure and batch JSONL include processing stages, content IDs, master selection, job dispatch, worker failure types, checkpoint recovery, elapsed times and final states. |
| Uncertainty | SYNTHETICALLY VALIDATED within model | Independent mixture calculation and Monte Carlo identify clipped read noise as the zero-signal bias. An optional independent signal model removes the plug-in term under its stated assumptions. Full covariance and detector-specific model error remain unmeasured. |
| Operational engineering | SOFTWARE TESTED on Windows | Two workers on full-size 2180 × 3856 FITS, 8 and 16 frames. Forced process termination and restart tested on a separate three-frame full-resolution job. Storage power-loss durability and sustained live observing were not exercised. |
| Clean installation | SOFTWARE TESTED on Windows | Fresh isolated Python 3.14 environment resolved the wheel and diagnostics dependencies from cached distribution wheels. See the fresh-install transcript and independent API and CLI smoke tests. Network dependency resolution was blocked at DNS. |
| GitHub infrastructure | IMPLEMENTED; hosted and advisory lookups BLOCKED | GitHub Actions defines Windows/Linux and Python 3.11–3.14, package smoke checks and dependency auditing. No configured remote or publication authorization. Live advisory resolution requires network access. |
| Whole product | SYNTHETICALLY VALIDATED within exercised cases | See tests, truth comparisons, synthetic WCS and benchmark evidence. Local HTTP listener fixture was blocked by WinError 10013. Real ANSVR and Nova operation remain blocked here. |
| Release | SOFTWARE CANDIDATE | Private artifacts for independent review. Hosted CI, live Gaia and solver checks, instrument calibration and production acceptance remain open. |

## Uncertainty experiment

For a true zero-light pixel, let (N) be the noisy dark-subtracted raw
signal. The plug-in photon term (max(N,0)) has positive expectation because
it clips all negative noise excursions. The interval width also depends on
the same noise draw used to compute the residual. Enumerating the Poisson
dark counts independently and integrating the Gaussian read noise predicts
a **9.010%** variance overestimate and coverage of **70.979%** at one ERR
and **96.801%** at 1.96 ERR. The 180,000-draw Monte Carlo measured a **9.06%**
overestimate and coverages of **70.92%** (95% interval 70.71–71.13%) and
**96.71%** (95% interval 96.63–96.80%). With independent known expectation,
the same mixture predicts **68.296%** and **94.997%**. These values describe
this zero-signal simulation. They do not impose Gaussian coverage on low
positive counts or measure real detector behavior.

Run `python benchmarks/zero_signal_reference.py` and
`python benchmarks/uncertainty_commission.py` to reproduce the comparison.

## Independent and installation results

Windows local tests returned 60 passed and one skipped on socket
permissions. Ruff lint and format, mypy and strict Twine passed.
The clean Windows environment chose NumPy 2.5.4, SciPy 1.18.1 and
Astropy 8.0.2 from cached wheel files with no shared site-packages.
The standalone installed CLI published two valid synthetic partial
products, both with QC PASS. The installed Python API independently
generated 37 checksummed files, detected six held-out catalogue
matches with 0.0402 arcsec RMS, and wrote measured diagnostic plots.

The independent CCDData comparison used 1280 synthetic pixels and found
maximum differences of 5.68e-13 ADU for SCI and 2.13e-14 ADU for ERR.
The three-light truth comparison gave median centroid errors of
0.030–0.035 px and normalized residual standard deviations of 1.013–1.017.
The deterministic truth catalogue serves the synthetic test only.

## Operational measurements

Windows 11 build 26300, Python 3.14.7 x64, 12 logical processors, NumPy
2.3.4, SciPy 1.18.1, Astropy 7.2.0, two workers and 4096 MiB configured.
RSS is sampled every 50 ms and sums the parent and child working sets,
which can count shared pages more than once. Product writes were approximately
1.21 and 2.42 GB. Both cases deliberately lacked a solver and published
valid partial products.

| Frames | Runtime | Peak summed RSS | Completed checkpoint reuse |
| ---: | ---: | ---: | ---: |
| 8 | 36.339 s | 1494.70 MiB | 0.088 s |
| 16 | 84.733 s | 1485.83 MiB | 0.136 s |

The recovery run terminated a separate worker after it created a staged
partial FITS. The first run yielded two published partials and one failed
frame. Restart retried the failed frame in 8.119 s. The incomplete stage
was never published. All three final products passed integrity audit and
all three raw digests matched. An abrupt termination can leave a staging
directory for inspection. Keep it separate from published products.

```powershell
python -m pip install ".[dev,diagnostics,benchmark]"
python benchmarks/batch_commission.py --shape 2180 3856 --cases 8:2 16:2
python benchmarks/full_resolution_recovery.py NEW_RECOVERY_DIRECTORY
python scripts/test_gaia_live.py NEW_GAIA_CACHE
```

## Full directive cross-reference

The [a6 accounting](directive-accounting-a6.md) retains the prior evidence
and describes the detailed historical requirements. This table records
changes and unresolved items for each section group.

| Sections | Current evidence and limits |
| --- | --- |
| 0–3 | Extended the existing a6 source. Offline calibration, QC, astrometry architecture and public software interfaces stay in the same repository. Scientific and production certification remain separate gates. |
| 4 | Existing scientific references plus an independent low-signal calculation. Unknown real detector quantities remain unset. |
| 5 | Rechecked the raw inventory of 98 files by SHA-256. Raw reduction supports a single uncompressed 2D image plane. |
| 6 | Matched calibration and independent scalar and CCDData comparisons. Real matched darks, flat-darks and replacement flats require telescope access. |
| 7 | Isolated the low-signal plug-in bias and added optional independently evidenced expectation. Shared-master, spatial and full covariance still require model extensions or physical measurements. |
| 8 | DQ regression tests and existing conservative impulse flagging. No pixel-repair capability is claimed. |
| 9 | Added measured distributions and source overlays. Dense-field deblending and night-long focus analysis remain outside the tested QC domain. |
| 10 | Existing local, online and authorized AUTO fixture coverage. Real solver tests require an accessible ANSVR service or Nova access and authorized submission. |
| 11 | Automated Gaia retrieval, offline verified cache, epoch adjustment and expanded spatial statistics. A real WCS and reachable ESA catalogue are required for the real-field acceptance gate. |
| 12 | Seeded raw FITS and truth, with contention and interruption exercised by the actual job runner. Distribution supplies a synthetic example. |
| 13 | Independent scalar, CCDData, truth-field and statistical comparisons. Real repeatability and photometric acceptance require actual reference observations. |
| 14 | SCI/ERR/DQ and provenance integrity verified. Dynamic Gaia reference digest and exact ADQL are included in the astrometry report. |
| 15 | Full-size Windows runs, bounded two-worker measurement and killed-worker recovery. Live solver loads, power loss and observatory-scale metadata growth remain unverified. |
| 16–17 | Existing modules retained, with isolated TAP, diagnostics and event logging code. CI and contributor files included in source. |
| 18–19 | Fresh-environment public API and CLI workflows, measured diagnostics and correlated JSONL. See [operator guidance](../installation/operations.md). |
| 20 | Local tests and packaging checks executed. Loopback permissions stopped the HTTP listener test. Hosted systems require an authorized remote. |
| 21–22 | Licensing, contribution, security and citation metadata. Source and archive content checks plus clean-environment dependency consistency. Current advisory results require network and were unavailable. |
| 23 | [Detector acquisition checklist](../commissioning/FINAL-ACQUISITION.md). Conversion gain, read noise, linearity, dark stability and independent real exposures remain missing. |
| 24 | The latest-assignment matrix above updates the inherited [Section 24 matrix](release-a6.md). The unavailable live and commissioning classifications stay blocked. |
| 25 | Private delivery includes source, wheel, sdist, checksums, synthetic inputs and truth, and commissioning evidence. |
| 26–27 | CI definitions, contribution materials and archives prepared for GitHub review. Public publishing and hosted validation require owner authorization. |
| 28–30 | Inspection, implementation, truth testing, benchmarking, installation, packaging and release review performed locally. External blocks appear above. |
| 31–33 | Release candidate for Windows-tested software with synthetic science evidence. Real astrometry, detector science and production operations remain separate gates. |
