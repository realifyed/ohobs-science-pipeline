# Security

Report integrity or security defects privately. Use the GitHub Security tab's
private vulnerability report if it is enabled. Otherwise, contact the OHOBS
maintainers through a private channel and ask where to send a report.

Include the OSP version, affected component, environment, and a small synthetic
reproduction. Share observational files, raw FITS headers and processing logs
only through an approved channel after removing identifying metadata.

Treat any disclosed Astrometry.net API key as compromised. Revoke and rotate
it through the service before reuse. Provide credentials
only through the local process environment as `OSP_ASTROMETRY_API_KEY`.
The public `.env.example` intentionally leaves it blank. The
[Nova credential guide](docs/installation/ONLINE_ASTROMETRY.md) covers setup.

Public CI uses local fixtures for solver coverage. Nova payloads require
explicit operator authorization. Never add live solver credentials, catalogue
receipts, or proprietary observing data to a public issue, pull request, or log.
