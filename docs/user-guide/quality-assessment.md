# Image-quality assessment

`osp qc PRODUCT --config observatory.yaml` reads a calibrated product and prints
fresh JSON measurements without modifying it. Reduction also writes qc.json.
The quality configuration controls background tiles, detection sigma, optional
smoothing, fit radius and source limits. Optional min_sources, max_fwhm_px,
warn_fwhm_px and max_ellipticity encode operator acceptance criteria.

OSP fits isolated candidates with an elliptical Gaussian plus a local constant.
FWHM is the geometric mean of fitted axes, ellipticity is 1 - minor/major.
Reports include source_count, fitted sources and background/PSF summaries.
DQ exclusions, edges and blends limit usable detections. Saturation rejection
requires a measured settings-specific threshold. Optional cosmic candidate
screening flags impulses but does not replace pixels.

Profile choices are GENERAL_SCIENCE, PRECISION_PHOTOMETRY and ASTROMETRY.
QC status and pipeline completeness are separate: COMPLETE can coexist with
QC FAIL. Undersampling, crowding, non-Gaussian PSFs and extended backgrounds
limit these metrics. Model flux/SNR use diagonal errors and are not an absolute
photometric calibration. Angular scales require accepted WCS.
