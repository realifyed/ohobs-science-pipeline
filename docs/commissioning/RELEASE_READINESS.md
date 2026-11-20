# Release readiness

**Decision: retain alpha, 0.1.0a2.** Incremental fixes harden flat lineage, constant-flat rejection, uncertainty status and validation, provenance linkage and catalogue-unit handling. Previous scientific products should be regenerated for re-evaluation if their state or compatibility is in question. The version change prevents normal cache reuse of a1 products.

| Gate | Status | Evidence or work to close |
| --- | --- | --- |
| Arithmetic, uncertainty semantics, FITS and compatibility | VERIFIED on named synthetic fixtures. PARTIALLY VERIFIED scientifically beyond those tests. | Source audit, regressions, bright-signal coverage and independent comparison. Keep covariance caveats with data. |
| Historical OHOBS inputs | VERIFIED metadata and per-pixel code inventory. FAILED as a complete commissioning set. | Zero matching darks. Three O flats are effectively clipped. Confirm units and optical configuration; replace or screen flats and capture matching independent dark groups. |
| Physical gain, saturation, current and temperature allowance | UNVERIFIED. | Execute characterization protocol and held-out dark/flat checks. A provided camera setting, storage code or synthetic gain is insufficient evidence. |
| Science ERR coverage | VERIFIED conditionally at high synthetic signals. PARTIALLY VERIFIED model at low signal; real sensor performance UNVERIFIED. | Report repeat-field aperture residuals, covariance, zero-signal empirical coverage and dark stability. |
| Astrometry | VERIFIED synthetic WCS and mocked solver. FAILED local live attempt. | Install known-independent Astrometry.net indexes and obtain real Gaia-held-out residuals at per-light pointings. |
| Operation and recovery | PARTIALLY VERIFIED. | Local tests and throughput runs exercise retry and atomic publication. CI on supported platforms, power-loss behavior, long full-size datasets, and routine handling of a mutable registry remain open. Completed SQLite receipts do not revalidate every persisted file on a no-op resume; use product validation if integrity is questioned. |

Keep acquisition originals immutable and avoid using simulated calibrators for observational products. For named files and exact reproduction, use [the inventory](OHOBS_FITS_INVENTORY.csv), [capture requirements](CAMERA_CHARACTERIZATION_REQUIREMENTS.md), [science report](SCIENTIFIC_VALIDATION_REPORT.md) and [benchmark report](PERFORMANCE_BENCHMARKS.md).
