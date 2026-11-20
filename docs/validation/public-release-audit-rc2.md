# OSP 0.1.0rc2 integration and public pre-release audit

## Scope

The original `v0.1.0rc2` tag captured the post-a4 work in a single commit.
RC1 was previously tested and archived without a Git tag. The audited RC1
source archive is the comparison baseline. The public-audit revision changes
release documentation, CI coverage and installation verification. The
installed Core and Simulation source modules are unchanged from the RC2 tag.

| Area | Integration evidence |
| --- | --- |
| Gaia DR3, epoch and proper motion | Gaia retrieval and cache modules and the shared astrometric verification implementation match RC1. Tests use a controlled catalogue, including proper motion, RA wrap, an offline cache replay and rejection cases. |
| Local and online solvers | ANSVR HTTP, local executable and authorized Nova support match RC1. The test suite exercises protocol fixtures. |
| Diagnostics and events | Plotting, JSON Lines events and reporting match RC1. The installed smoke test verifies a published WCS and generates an HTML report and four measured diagnostics. |
| Uncertainty | The marginal propagation equation and zero-signal reference are retained. The optional independent photon expectation must now match the observation's origin as well as its geometry, unit and hash. |
| Calibration, QC and DQ | Matching checks detector and exposure metadata, flat-dark lineage and data origin. Calibration normalization and SCI arithmetic, QC and mask calculations are retained. Conditional ERR and provenance checks remain in place. |
| Batch and recovery | The recovery implementation is retained. RC2 adds admission checks for mixed origins before dispatch. The full-resolution forced-termination benchmark checks retry and published product integrity. |
| Simulation | The generator lives in a separate distribution and declares its dependency on Core. Core has no reverse import or dependency. |

## Science evidence and limits

The WCS fixture compares a known **synthetic** sky solution with held-out
measured centroids. Its six matches and approximately 0.0402 arcsec RMS
measure synthetic fixture agreement. They provide no estimate of on-sky
accuracy. The independent scalar and Astropy CCDData comparison checks
arithmetic under the declared marginal-noise model. It cannot establish
real detector noise, common calibration covariance or real photometry.

See the [model assumptions and limitations](../science/assumptions-and-limitations.md),
[RC1 methods and operational evidence](release-rc1.md) and the
[MiniCam8 acquisition checklist](../commissioning/FINAL-ACQUISITION.md).

## Installation and reproduction

Use the [bundle installation instructions](../../README.md) or the
[simulation and configuration guide](../installation/SIMULATION-MIGRATION.md).
From the unpacked source tree, build with `python -m build --outdir dist`
and `python -m build packages/osp-sim --outdir dist`. Run both installation
smokes using `scripts/check_wheel.py`. The tests and scientific benchmarks
use the same source tree, and the frozen synthetic fixture carries a digest
manifest. The release bundle includes package checksums and measured audit
outputs. Use checksums to verify a delivered byte-for-byte copy.

## Public release gates

- Locally exercised platform: Windows with Python 3.14. The CI workflow
  defines Windows and Linux checks for Python 3.11–3.14. Hosted execution
  requires an authorized GitHub repository.
- Fresh local installations can use cached wheel files when package-index
  access is unavailable. Linux, earlier Python versions and the networked
  dependency advisory check require separate execution.
- Real ANSVR or Nova solving, live Gaia verification, a qualified MiniCam8
  data product and sustained observing-night operation remain separate gates.
- The prepared public source snapshot omits Git metadata and private inputs.
  Review historical commit metadata and superseded commissioning notes
  before authorizing external publication of the original local Git history.
