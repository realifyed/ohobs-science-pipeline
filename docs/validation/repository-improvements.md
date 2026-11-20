# Repository improvement verification — 2026-11-20

This record supplements historical validation; it does not replace or revise
prior scientific evidence. Version remains 0.1.0rc2. Numerical calibration,
uncertainty, DQ and PSF algorithms are unchanged.
Gaia VOTable ingestion received a targeted compatibility fix described below.

The public documentation now starts with source installation, separates generic
observatory setup from OHOBS-01, and covers ingestion, calibration, QC, astrometry,
products, reporting, recovery and development. Generated configuration schema
and installed CLI help are checked by scripts/check_docs.py. Core's source
distribution includes these references and the frozen fixture.

Windows CPython 3.14.7 is available. WSL enumeration outside the sandbox returned
no distributions; Linux execution is unavailable. Windows/Linux Python 3.11–3.14
remain CI targets; hosted execution and macOS are not asserted verified.

Initial Core tests: **62 passed, 2 simulator modules skipped** (simulator absent).
Fresh combined source environment: **67 passed, no skips**, followed by
**70 passed, no skips** after three portability/configuration tests were added.
The final suite after the Gaia field-ID regression passed **71 tests with no
failures or skips**. Ruff check and formatting passed for 57 files; Mypy passed
for 28 source files.
All **14 final release checks passed**, including installed source and wheel
workflows, generated documentation checks and live Gaia cache replay. Curated
historical JSON/JSONL and commissioning transcripts are explicitly included in
the Core sdist alongside the final verification record.
Fresh source install
used --no-cache-dir and downloaded dependencies from the configured index,
including NumPy 2.5.5, SciPy 1.18.1, Astropy 8.0.3 and Pydantic 2.14.4.
This differs from the original local dependency set and passed scientific tests.

Core-only and combined wheel installations passed pip check, CLI help/doctor,
master generation, reduction, product and provenance validation. Core-only
source installation also passed in a new isolated environment without simulator
or matplotlib. Combined API smoke passed synthetic truth residual checks and
injected WCS verification; this does not demonstrate a live solver.

Both package builds produced sdists and wheels rebuilt from sdists. All four
artifacts passed strict Twine metadata checks. The first sandboxed Twine attempt
could not read a wheel; the same check outside the sandbox passed. Ruff and
Mypy passed at baseline; final checks and sanitized transcripts accompany this
record. Documentation API execution produced a valid PARTIAL synthetic product
with conditional uncertainty, failed/unavailable external WCS and QC FAIL on
the tiny fixture, which is an expected measurement rather than a test failure.

Final numerical and integration evidence:

- [Release-check transcript](repository-verification.json): command lines, exit
  codes and captured output, with personal repository/home prefixes redacted.
- [Additional scientific experiments](repository-science-checks.json): simulator
  truth validation, Astropy CCDData/scalar reference comparisons (ccdproc was
  unavailable), and low-count/shared-calibrator uncertainty experiments.
- The source-based PowerShell simulator tutorial completed generation with
  seed 1234, master construction, reduction, validation, HTML reporting and
  batch processing of three lights. External WCS remained unavailable.
- Three added regression tests cover YAML-relative paths independent of working
  directory, nested mixed-case FITS extensions and generic configuration without
  invented physical measurements or upload permissions.
- Shared modules already use pathlib, case-normalized FITS suffixes, subprocess
  argument lists and explicit platform lock/solver adapters. No proven numerical
  or shared-runtime portability defect required an algorithm change. The public
  guides now explicitly distinguish native solve-field from HTTP local/auto.
- Corrected an existing claim that standalone WCS verification never accesses
  the network: Gaia reference retrieval follows the configured explicit opt-in,
  including during verification. Offline operation requires a local reference
  or cache with networking disabled.
- A live ESA query exposed an actual parser defect: FIELD ID="SOURCE_ID" and
  name="source_id" were read using the ID. OSP now requests VOTable names.
  An offline regression covers both ID spellings. The live fetch and offline
  cache replay then passed with 262 catalogue rows. Initial rejected responses
  were not evidence of an ESA outage. No calibration equation changed.

During targeted Gaia verification, sandbox access to pytest's shared temporary
directory and the network was denied. Repeating those checks outside the
sandbox passed (five Gaia tests and live fetch/cache replay). These were
environment setup/access failures, not numerical regression failures.

Editable installation of both packages also succeeded. Source installation was
verified both with fresh downloaded dependencies and with Core alone. Tests and
installed checks establish the current Windows software behaviour; they do not
establish other Python versions, Linux operation, instrument measurements or
external solver availability.

No personal development path was found in public README, documentation, configs
or shared Python source. Generated environments/builds stay ignored. Historical
references to absent private inventories are labeled as unavailable rather than
linked as public assets. Historical evidence and raw data are preserved.

Remaining verification needs actual hosted CI runs, Linux runtime/solver indexes,
live Nova/native solver integration and real detector/on-sky commissioning. Repository
source review does not authorize publishing historical git objects: review the
[publication runbook](../installation/GITHUB-RELEASE.md) before pushing history.

The updated source tree is prepared for public publication as a scientifically
transparent release candidate. This audit does not establish production detector
commissioning, other interpreter/platform execution or hosted CI success.
No remote push or GitHub release was performed.
