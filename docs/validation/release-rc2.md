# OSP 0.1.0rc2 release assessment

OSP Core stays at the repository root. The separately built Simulation
distribution lives under `packages/osp-sim`. Scientific validation stays
in the shared source checkout as tests and executable reference comparisons.

## Local evidence

- The pre-change Windows Python 3.14.7 suite recorded 60 passes and one
  loopback-permission skip.
- At seed 1234, before-and-after runs reduced three 96 × 128 synthetic
  lights. Maximum absolute changes in SCI and ERR were 0 ADU; the DQ arrays
  matched exactly. The sampled raw bias and light arrays and all FITS truth
  planes matched exactly. FITS file and product digests change when origin
  headers and provenance change.
- In an independent 1280-pixel comparison with Astropy CCDData, the
  maximum differences were 4.69e-13 ADU in SCI and 1.60e-14 ADU in ERR.
  The script also runs a scalar reference. The source data remain seeded
  and the prior scientific tolerances apply.
- Core-only and combined installation checks target distinct isolated
  virtual environments. The frozen example makes Core-only reduction
  independent of Simulation. The combined check generates two datasets
  with matching manifests and verifies a full reduction with a controlled
  WCS fixture and independent reference matches.
- The original 98 OHOBS raw FITS files matched the pre-commissioning
  inventory digests. The public test data are generated fixtures.

See the delivery archive for exact test summaries, install outcomes,
checksums and numerical results. The [migration guide](../installation/SIMULATION-MIGRATION.md)
documents command changes and reproduction instructions.

## External gates

The GitHub Actions workflow is present for Windows and Linux. Hosted
results require an authorized repository. Package-index publication was
outside this delivery. Dependency resolution for local installation used
cached distribution wheels. The real instrument and production-release
gates from [rc1](release-rc1.md) still apply, including a verified real
astrometric solution, measured detector properties, matched real
calibrations, and withheld validation exposures.
