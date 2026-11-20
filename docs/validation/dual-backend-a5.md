# OSP a5 dual-backend validation and release readiness

| Area | Evidence |
| --- | --- |
| ANSVR HTTP | Existing contract tests and local adapter retained. The development host could not connect to the installed service. |
| Nova HTTPS | Simulated HTTP lifecycle checks exercise authorization, retry, source coordinates, multipart FITS, timeouts, failure, restart recovery, and redaction. Live Nova DNS resolution from the execution host failed. No rotated credential was present in its process environment. |
| Real source extraction | The selected Lagoon O-filter exposure yielded 49 fitted candidates and its input SHA-256 remained unchanged. No authenticated upload, submission ID, job ID, WCS or real Gaia residuals were obtained in this sprint. |
| Scientific acceptance | Synthetic WCS and Gaia checks exercise the common verification path. Whole-image and manually attached solves remain unverified diagnostics. |
| Release | Engineering alpha. Live acceptance for both solvers, real Gaia verification, detector characterization, matched calibration and production operation remain open. |

Use [Nova commissioning](../installation/ONLINE_ASTROMETRY.md) and
`scripts/Commission-Nova.ps1` on a network-enabled host. The script probes
first, reads a rotated key through a secure prompt when needed, and submits
centroids of the supplied real FITS only with `-AuthorizeUpload`. Return a
redacted validation report and candidate WCS through the intended private
channel. The existing [detector checklist](../commissioning/FINAL-ACQUISITION.md)
remains the basis for real calibration assessment.
