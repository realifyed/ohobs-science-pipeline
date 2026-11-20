# Scientific validation report

This report covers OSP 0.1.0a2. The Windows test suite passed all 30 cases. It separates synthetic verification, comparisons and observational commissioning. Machine-readable outputs are [reference.json](reference.json), [tests.log](tests.log) and inventory.log (local commissioning record; not distributed).

| Evidence | Status and result |
| --- | --- |
| Controlled zero, negative and bright signal | VERIFIED in synthetic fixtures. Dark offset is removed once, normalized flat preserves sign, and invalid input produces NaN rather than a plausible calibrated value. |
| Master uncertainty | VERIFIED for a synthetic mean combine. Independent calculations reconstruct dark and flat-dark sample variance over n and include the common flat-dark estimator variance exactly once in the flat. The deterministic median and clipped-mean tests exercise their code. Coverage under real correlated outliers is UNVERIFIED. |
| Bright Monte Carlo | VERIFIED for 85,000 independent pixels at 2,400 e− before the 0.85 flat response. Mean z −0.010564, standard deviation 1.000321, 1σ coverage 68.2835%, 1.96σ coverage 94.9918%. The variance ratio for repeated 25-pixel sums was 1.020107. Acceptance accounts for sample size and first-order terms. |
| Lower signal | PARTIALLY VERIFIED. Existing 70,000-trial tests show the expected upward variance bias around zero. The independent 1,280-pixel reference scene had mean z −0.005783, SD 1.022333, 1σ 67.50% and 1.96σ 93.36%. The latter is below nominal 95% in this scene. This is evidence for conditional reporting, not precision coverage for all scenes. |
| Aperture signal truth | VERIFIED only for the synthetic scene and chosen aperture. The 154-pixel background-subtracted aperture measured 12674.32 ADU versus 12538.69 ADU expected, a +135.63 ADU (+1.082%) single-realization difference. Calibration comparison below distinguishes recovery from agreement between calculators. |
| Calibration compatibility | VERIFIED in tests for exposure, temperature, filter, camera ID, readout, gain, offset, binning, ROI, unit and transitive flat-dark tolerance. No positive temperature allowance for Node 01 has been validated. |
| DATA/ERR/DQ and provenance | VERIFIED with FITS checksums, invalid masks, absent or partial uncertainty, finite negative SCI, consistent units, WCS status, and immutable original input in integration tests. Checksums alone would accept deliberately resaved semantic contradictions; a2 rejects them. |
| QC and astrometry | VERIFIED under injected isolated Gaussian sources and synthetic WCS/epoch/geometry tests. Solver retry uses a mocked backend; generated tests include a wrong pointing and incompatible catalogue units. Real accuracy and deblending are UNVERIFIED. |
| OHOBS | VERIFIED ingestion and physical-code inventory of all 98. FAILED attempted real reduction due to absent calibration metadata and darks; live Astrometry.net also unavailable. Hence real calibrated flux, ERR coverage, WCS match count, residual RMS and outlier fraction are UNVERIFIED. |

## Independently configured references

The reference rebuilds the three masters from supplied synthetic exposures, with fixed median normalization and matched unscaled darks. Astropy CCDData is an established workflow but shares the FITS library and array ecosystem used in OSP. A second implementation uses Python standard-library scalar statistics for mean, variance and normalization and evaluates the uncertainty derivatives separately. It shares only the input arrays/FITS loader with OSP, and independently checks arithmetic, not real-camera assumptions. Stand-alone ccdproc was unavailable, and pip reported DNS failure. The comparison script will use ccdproc automatically if installed. These comparisons avoid comparing two reductions that reuse OSP's masters.

| Comparison | Max absolute pixel Δ | RMS pixel Δ | Aperture Δ | Max absolute ERR Δ | Max absolute row mean Δ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Astropy CCDData | 4.41e−13 ADU | 1.49e−13 ADU | −1.62e−12 ADU | 1.78e−14 ADU | 6.43e−14 ADU |
| Independent scalar | 3.69e−13 ADU | 1.10e−13 ADU | +2.60e−12 ADU | 1.24e−14 ADU | 3.55e−14 ADU |

All four quadrant mean deltas were below 2e−14 ADU in magnitude; no quadrant or row pattern above double-precision arithmetic was detected. This scope implements the same statistical model, so reference agreement cannot detect a shared modeling mistake such as neglected flat normalization covariance. [Astropy CCDData](https://docs.astropy.org/en/stable/nddata/ccddata.html) · [ccdproc flat normalization](https://docs.astropy.org/projects/ccdproc/en/stable/api/ccdproc.flat_correct.html)

## Reproduction

- `python -m pytest -q -s` runs regression, simulation and recovery tests. Acceptance limits are in test code.
- `python benchmarks/commission_reference.py dist/new-synthetic-case` regenerates the explicitly synthetic test observations and references. It uses a distinct camera ID, geometry, timestamps and optical ID. The injected conversion factor is solely simulation truth.
- See [REAL_DATA_ANALYSIS.md](REAL_DATA_ANALYSIS.md) for the procedure and blockers for physical commissioning.
