# Release status

**OSP 0.1.0rc2** is a scientific software pre-release for Open Horizon
Observatory. Use the source archive and matching verification evidence
from the same release bundle.

| Gate | Status |
| --- | --- |
| Detector calibration and masks | Synthetic calibration, masks, uncertainty propagation and independent CCDData and scalar comparisons passed under the specified marginal-noise model. |
| Astrometric verification | A controlled synthetic WCS produced six held-out matches at about 0.0402 arcsec RMS. This describes fixture agreement. |
| Raw integrity and provenance | Synthetic FITS and product provenance checks passed. The 98 real raw FITS digests were preserved during commissioning. |
| Local release verification | Windows and CPython 3.14.7. The audited CI definition covers Windows and Linux on Python 3.11–3.14. Hosted results and the other platform/interpreter combinations are unverified. |
| Real solving and detector commissioning | Live plate solving, an independent real Gaia result, a scientifically validated MiniCam8 product, and observing-night operation remain pending. |

Measure the MiniCam8 conversion gain, read noise and linearity with matching
detector settings. Acquire matched darks and flat-darks, replacement O-filter
flats and independently withheld validation exposures. Verify a real WCS
against an independent Gaia catalogue before claiming on-sky accuracy.

See the [RC2 integration audit](public-release-audit-rc2.md),
[uncertainty and calibration limits](../science/assumptions-and-limitations.md),
and [commissioning acquisition checklist](../commissioning/FINAL-ACQUISITION.md).
