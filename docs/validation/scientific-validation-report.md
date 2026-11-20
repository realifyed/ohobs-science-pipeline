# OSP 0.1.0a3 scientific validation and release decision

The [a5 dual-backend validation](dual-backend-a5.md) supplements the calibration
evidence preserved in this report.

**Decision: retain alpha.** VERIFIED describes a directly observed result within
the stated scope. PARTIALLY VERIFIED describes a restricted demonstration.
UNVERIFIED means evidence is missing. FAILED identifies an attempted check with
an observed failure or unmet criterion.

Local Windows checks passed 34 pytest cases, Ruff lint and format checks, and
mypy on 17 source files. The wheel installed in a fresh virtual environment
using the existing local runtime dependencies. Its CLI and synthetic
end-to-end reduction passed an installation smoke test. Both distributions
passed Twine metadata checks.

| Acceptance area | Status and evidence |
| --- | --- |
| FITS ingestion and raw immutability | VERIFIED for 98 supplied FITS files. All 98 SHA-256 digests matched on a second read. Synthetic tests exercise unsigned scaling, BLANK, truncation, checksum and contradictory DQ or WCS metadata. |
| Master selection and calibration | VERIFIED on synthetic matched-dark and flat-dark cases, including intentional mismatches, negative science values, explicit overrides and flat lineage. FAILED real selection for all 38 lights. No dark or flat-dark was supplied. Only matched-dark plus flat-dark science correction is implemented. The registry can build BIAS masters for characterization. |
| Scientific units, masks and uncertainty | VERIFIED for the tested synthetic model and product checks. PARTIALLY VERIFIED overall. Low signal has known upward variance bias. Conditional ERR excludes flat normalization uncertainty, shared-master covariance, spatial covariance and systematic mismatch. Some DQ codes are reserved for future detection or interpolation. |
| OHOBS detector characterization | VERIFIED raw header settings and storage encoding. UNVERIFIED conversion gain per stored ADU, read noise, saturation, linearity, dark structure, timing accuracy, full camera transfer behavior and calibration temperature tolerance at Node 01. |
| Flats | VERIFIED that three O flats have over 99% of samples at code 65520. FAILED as a usable unscreened master set. The new opt-in maximum-code occupancy check is tested on synthetic flats. The physical onset of saturation remains UNVERIFIED. |
| Image quality | VERIFIED for tested injected isolated Gaussian models and the optional smoothed candidate pass. Real PSF accuracy, crowded fields, extended-emission bias, and science-profile thresholds remain UNVERIFIED. No general deblender, trail detector or cloud classifier is provided. |
| Astrometry | VERIFIED synthetic pixel origin, SIP, parity, epoch motion, wrong-solution checks and mocked holdout, timeout and retry for native and ANSVR backends. FAILED live Windows ANSVR launch. Real independent Gaia residuals and production solver timing are UNVERIFIED. |
| Products and operation | VERIFIED synthetic end-to-end PARTIAL FITS, linked provenance, checksums, atomic publication, crash retry, cache reuse and changes in external catalogue identity. PARTIALLY VERIFIED job reliability. Process-kill recovery is tested. Power-loss durability and in-flight changes to files or indexes remain unverified. |
| Distribution and support | Local Windows Python 3.14 is exercised. The matrix is configured for Windows and Linux with Python 3.11 and 3.14. Hosted CI, support on other environments, and long full-size real runs remain UNVERIFIED. BSD-3-Clause package includes reproducible synthetic generation. |

## Scientific comparison

The injected 1280-pixel independent comparison used Astropy CCDData and separate
scalar arithmetic with the same matched-dark model. Against CCDData, OSP SCI
differed by at most 4.55e-13 ADU and one-sigma ERR by at most 1.78e-14 ADU.
Normalized residuals against injected truth had a mean of -0.0058 and standard
deviation of 1.0223. Coverage was 67.5% at one sigma and 93.4% at 1.96 sigma.
The injected aperture total was 12538.69 ADU and the recovered value was
12674.32 ADU in this one realization. These runs validate the stated synthetic
arithmetic and conditional model. ccdproc was unavailable. The same physical
assumptions are shared across the arithmetic comparison.

## Observational checks

The supplied Lagoon set has 60 flats and 38 lights, totaling 1,648,281,600 bytes.
The lights have 120 s exposure and measured CCD-TEMP values of 18.9 or 19.0 °C.
H-alpha flats are 3.75875 s and O flats are 5.02945 s, both at 18.8 °C. N.I.N.A.
records a 0 °C set point. The header-reported measured temperature governs
calibration matching. Use the exact settings and holdout capture plan in the
[characterization requirements](../commissioning/CAMERA_CHARACTERIZATION_REQUIREMENTS.md).
All light dry runs failed on zero compatible DARK masters after applying
provisional unit and optics overrides strictly for the dry runs. No real SCI,
ERR, or validated coordinates were produced. The three nearly uniform O flats
need replacement or exclusion, and the remaining flats need an independent
field-response check. The physical gain, camera time and optical identity need
operator evidence before science publication.

## Windows solver and source extraction

ANSVR 0.22 and 24 installed 2MASS-family indexes were readable. Loopback port
8080 was inaccessible in this session. Cygwin Bash exited with Windows code
`0xc0000142`, and Cygwin path conversion failed with WinError 623. Direct
execution of the native bundled binary returned the same DLL relocation error.
WSL reported access denied. The source-only diagnostic initially recovered no
candidates from one H-alpha and one O light with their respective unsmoothed
settings. An optional mask-normalized Gaussian detection pass with sigma 3 px,
fit radius 12 px, and threshold 6 times the original background RMS returned
49 fitted candidates in that H-alpha light. Fits used original pixels.
This run reached ANSVR path conversion and failed there. It produced no WCS.

## Performance

Windows 11 build 26300, AMD64 with 12 logical CPUs, Python 3.14.7,
NumPy 2.3.4, SciPy 1.18.1 and Astropy 7.2.0. A single full-size synthetic
2180 × 3856 reduction took 6.93 s, including 1.83 s in calibration and
3.00 s in QC. Dark, flat-dark and flat master builds took 3.17, 2.79 and
4.09 s, respectively, with five inputs per master. Peak process working
set was 834.4 MiB. A second invocation verified and reused the existing
product in 0.91 s. It was a PARTIAL product because the benchmark solver
was deliberately unavailable.

| 128 × 128 synthetic lights | Workers | Wall time | Sampled process-tree peak RSS | No-op resume |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 4.44 s | 243.6 MiB | 0.127 s |
| 10 | 2 | 24.18 s | 373.7 MiB | 0.112 s |
| 30 | 2 | 60.99 s | 375.2 MiB | 0.094 s |

Working-set samples were taken every 50 ms and can count shared pages twice.
The parent peak grew by 0.58 MiB between the 10- and 30-frame workloads.
This demonstrates bounded image-buffer usage for the tested workloads.
Path and checksum metadata still grow with file count. Full-size concurrent
production workloads, long-running stability and live solver memory are
unverified. See the [a2 commissioning measurements](../commissioning/PERFORMANCE_BENCHMARKS.md)
for a separate earlier run up to 200 small frames.

## Close the release gates

1. Capture and independently validate the matched calibration groups and
   detector measurements. Quantify dark residuals, flat repeatability, aperture
   errors and covariance using withheld acquisitions.
2. Follow [Windows ANSVR commissioning](../commissioning/ANSVR-WINDOWS.md) and
   record actual solves, held-out Gaia DR3 residuals and failure cases.
3. Run the hosted OS matrix and a full-size concurrent night. Record wall time,
   memory, solver failures, controlled interruption, resume, and publication checks.

The [scientific assumptions](../science/assumptions-and-limitations.md) and
[references](../science/references.md) accompany these results.
