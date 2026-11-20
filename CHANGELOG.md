# Changelog

## 0.1.0rc2

- Added source-first Windows/Linux guides, generic observatory configuration,
  scientific workflow documentation and generated schema/installed CLI reference.
- Extended independent installed CLI checks to metadata, QC and HTML reporting;
  added documentation consistency checks to CI. Numerical algorithms are unchanged.
- Fixed Gaia TAP VOTable ingestion to prefer column names over XML IDs; ESA's
  uppercase SOURCE_ID field ID no longer rejects an otherwise valid catalogue.
- Split seeded FITS generation into the independently packaged
  `ohobs-science-sim` distribution. Use `osp-sim generate`.
- Added explicit synthetic test mode and checked the origin of raw frames,
  master lineage, batch inputs and published science products.
- Added independent Core-only and combined installation checks and a frozen
  synthetic validation fixture. Calibration equations and QC algorithms are unchanged.

## 0.1.0rc1

- Added automatically retrieved, checksummed Gaia DR3 field catalogues and offline replay.
- Added measured diagnostics for exposures, masters, calibration residuals, astrometry,
  uncertainty coverage and performance.
- Added correlated JSON Lines for worker execution, calibration selection and recovery.
- Added an independent photon-expectation path and a separate low-count reference calculation.
- Added an installation check in fresh virtual environments and a full-resolution crash benchmark.

## 0.1.0a6

- Added seeded synthetic FITS generation with detector and celestial truth, and a separate adversarial input set.
- Added evidence-gated short-exposure bias-only reduction, optional impulse candidates, and QC sharpness and elongation reporting.
- Added exposure and batch JSON/HTML reporting and instrument, dependency, storage and solver readiness checks.
- Retained the local, online and authorized AUTO astrometry backends.

## 0.1.0a5

Added local, online, and local-first astrometry modes. Nova uses a rotated
environment credential, private-by-default centroid submissions, and durable
receipts with bounded polling, restart recovery, and an opt-in image mode.
All WCS candidates use the existing geometry and Gaia acceptance checks.

## 0.1.0a4

Added the loopback ANSVR 0.22 HTTP backend and Windows diagnostic script,
installed-environment diagnostics, and read-only auditing of checkpointed FITS
products. Added low-count and shared-calibration numerical checks and
full-detector batch benchmarks. See the final commissioning reports for the
remaining live-solve and physical calibration gates.

## 0.1.0a3

Added a local Windows ANSVR adapter, a solver launch probe and raw-light
astrometry diagnostics. Retain candidate WCS separately and include solver
and catalogue file digests in batch identities. Added an opt-in flat
peak-code occupancy screen and optional smoothing for source detection.
See the scientific validation report for
evidence and outstanding release gates.

## 0.1.0a2

Commissioning fixes for transitive flat-dark matching, degenerate flats, ERR coverage,
SCI/DQ and WCS semantics, provenance linkage and Gaia table units. See the
commissioning reports for synthetic verification and real-data blockers.

## 0.1.0a1

Alpha with FITS ingestion, matched masters, detector calibration, conditional uncertainty, DQ, image QC, local astrometry adapter, catalogue residuals and resumable batch execution.
