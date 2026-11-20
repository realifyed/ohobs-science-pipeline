# Full implementation directive accounting

The [acceptance matrix](release-a6.md) records Section 24 results. This
cross-reference tracks the rest of the directive and explicitly identifies
remaining limitations.

| Sections | Evidence or limitation |
| --- | --- |
| 0–3 | Implemented in the existing repository. Confirmed committed a4, verified initial a5 changes, and built a6. The product remains an engineering alpha. |
| 4 | Scientific methods and references in `docs/science`. Instrument quantities without measurements remain unset. |
| 5 | Strict read-only FITS ingestion, metadata, scaling and truncation regressions; multi-extension science products supported. Raw reduction requires a single uncompressed 2D image plane. |
| 6 | Software-tested matched darks, flat-darks, independent bias-only mode, compatibility and robust masters. Measured detector defects are configured; no physical characterization was possible here. |
| 7 | Independent comparison and Monte Carlo evidence. The zero-signal offset and correlated errors constrain interpretation. Full covariance planes and an instrument-specific noise model remain open. |
| 8 | Stable mask bits, including software-tested optional isolated impulse screening. No interpolation feature. |
| 9 | Background, counts, robust local fits, width, sharpness, SNR, elongation and configurable warning. Focus time-series and reliable crowded-field deblending remain incomplete. |
| 10–11 | Local, online and authorized AUTO tested with protocol fixtures; shared geometry, local catalogue cache, epoch matching and residuals tested synthetically. Automated Gaia retrieval is not included. Real solve and actual Gaia acceptance are BLOCKED. |
| 12 | Six seeded profiles and adversarial files, truth FITS and catalogues, checksums, valid outputs kept separate from injected failures. Interrupted fixture is exercised through the job engine. |
| 13 | Three-light truth comparison, Astropy CCDData and scalar comparison, statistical coverage and synthetic WCS. Real repeated-field photometry remains BLOCKED. |
| 14 | Validated SCI, ERR, DQ, hashes, science identity, sidecars. Field catalogue uses a local ECSV; external provenance must be supplied for a real run. |
| 15 | Batch checkpoint tests, input limits, worker limits, retries, atomic publication and performance logs. Large-scale metadata growth, live solver throughput and power-loss recovery remain unverified. |
| 16–17 | Existing modular structure preserved, documented Python interfaces and optional benchmark dependency. Source distribution includes CI and issue/PR templates. |
| 18–19 | Installed workflow, doctor, simulator, status/report CLI, JSON and printable HTML. Batch reports give timings and integrity; process-tree memory is benchmark-only. Diagnostic plots and comprehensive structured event logging remain incomplete. |
| 20 | Full local tests, static checks and installed-wheel workflow. The local socket fixture was permission-blocked. Hosted Windows/Linux matrix and fresh network dependency install remain BLOCKED. |
| 21–22 | BSD-3-Clause, contribution, citation and release documentation. Credentials, raw observations, directives and caches excluded. Dependency constraints and offline consistency checked; current CVE resolution and a formal SBOM remain unavailable. |
| 23 | Detector acquisition and withheld-frame procedure prepared. Real conversion gain, read noise, saturation, dark stability and science acceptance remain BLOCKED. |
| 24 | Acceptance matrix evaluated in `release-a6.md`. |
| 25 | Private bundle includes source, wheel, sdist, checksums, tests, synthetic sample and reproducible evidence. |
| 26–27 | No publication. Adversarial tests revealed and corrected deterministic FITS checksum stamping and source/impulse separation. Remaining limits appear above and in `release-a6.md`. |
| 28–30 | Implemented, tested, benchmarked, built and reviewed the feasible workflows with environment limits documented. |
| 31–33 | Engineering alpha. Offline calibration and reporting demonstrated under test conditions. Live solver acceptance, real calibration and sustained operation require commissioning. |
