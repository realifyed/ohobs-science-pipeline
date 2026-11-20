# Science methods and limitations

An offset-bearing matched dark D is subtracted once. C = (R − D)/F retains sky and negative values. F is the combined, dark-corrected flat divided by the median of finite, unflagged pixels. The same flat-dark applies once after combination. Flats require stable illumination and homogeneous exposures. They match filter and optical configuration. The normalized flat response is assumed stable across science temperatures for the intended use. Darks match camera, mode, gain, offset, geometry, binning, units, configured settings and exposure duration. The default temperature tolerance is zero. Widening it requires explicit evidence.

Mean estimator variance is sample variance over the contributing count. The median and single-pass median/MAD-clipped mean use deterministic entire-frame bootstrap resampling. Bootstrap variance is approximate at low sample counts. The dark temporal variance uses all finite unmasked samples, so strong transients can inflate it. The flat-dark uncertainty is added once following combination, and the normalization factor is treated as fixed.

Let N = R − D and g be electrons per ADU. First-order marginal variance is [max(N,0)/g + temporal dark variance + Var(D) + C² Var(F)]/F². Electron inputs use g = 1. The empirical dark temporal term contains single-exposure read and dark shot noise, and Var(D) adds the separate sampling error of the master. Near zero signal, the plug-in term has positive bias. Shared masters induce covariance across exposures. Readout correlations, flat normalization error, response drift, calibration/model covariance and gain uncertainty are outside the variance plane. An ERR map cannot substitute for validation of aperture or ensemble noise.

| Bit | Name | Meaning |
| --- | --- | --- |
| 0x0001 | NONFINITE | Raw NaN, infinity or FITS BLANK |
| 0x0002 | SATURATED | At or above measured raw threshold |
| 0x0004 | BAD_PIXEL | Operator-supplied detector defect |
| 0x0008 | HOT_PIXEL | Operator-supplied measured detector defect |
| 0x0010 | DEAD_PIXEL | Operator-supplied measured detector defect |
| 0x0020 | FLAT_INVALID | Nonfinite or low master response |
| 0x0040 | COSMIC_RAY_CANDIDATE | Optional isolated positive impulse screening |
| 0x0080 | EDGE | Reserved for an edge mask. QC excludes fitting boundaries. |
| 0x0100 | INTERPOLATED | Reserved for interpolated pixels |
| 0x0200 | CALIBRATION_SUSPECT | Invalid or insufficient calibration support |
| 0x0400 | NONLINEAR_RESPONSE | Above the measured linear maximum |

Flags are OR-combined. Fatal bits invalidate SCI and ERR. Saturation and linearity require settings-specific measurements. Pixel replacement is outside the correction model.

QC fits an elliptical Gaussian and local constant to isolated candidates. FWHM is the geometric mean of the two axes. Ellipticity is 1 − minor/major. Model flux and SNR assume the fitted profile and diagonal pixel errors. Extended emission can dominate tile-based background estimates. Blended peaks are excluded. Crowding, undersampling and non-Gaussian PSFs limit interpretation. Angular FWHM uses a local approximate scale only after WCS acceptance.

Astrometry holds out one in three detected sources and uses mutual-nearest Gaia matches. Proper motion is applied in the tangent plane against TCB Julian years. Parallax, perspective acceleration, atmospheric refraction, and chromatic displacement are outside the model. Match completeness, field coverage, residual RMS and operator-supplied catalogue-independence evidence are required. The software records solver errors separately from calibration and excludes unverified WCS from SCI. Real field accuracy is unverified.

To close release risks, acquire independent dark and flat-dark controls, a multi-level detector sequence and a documented independent catalogue for at least one reference field. Measure temporal and spatial correlations and calibrator stability before making absolute photometric or precision error claims.

For detectors and exposure regimes with measured negligible dark signal and
noise, `calibration.bias_only_max_exposure_s` plus
`calibration.bias_only_evidence` enables the explicit bias-only route.
Build separate zero-exposure bias masters for science and flats, each at the
matching temperature and detector configuration. The two sample sets must
be disjoint because the propagated ERR model assumes independent references.
Select using `masters build --bias-reference ID` and `calibrate --bias ID`.
The measured exposure limit applies to both light and flat. The example
MiniCam8 configuration keeps the matched-dark workflow.

An observation-linked, independently estimated expected signal can
replace the clipped observed numerator in the photon variance term and
in the flat-response derivative. The raw detector grid and units must
match. Photon expectation should include sky, remain nonnegative and
exclude bias and dark. The science equation still uses the actual
measured numerator. Pixelwise model uncertainty or systematic error
in this independent expectation is not propagated. The
[release validation](../validation/release-rc1.md#uncertainty-experiment)
shows why the default plug-in estimator gives biased variance at zero
signal without implying a Gaussian coverage requirement at low counts.

The optional `quality.cosmic_candidate_sigma` flags isolated positive
impulses against medians and conditional ERR. It preserves SCI values and
excludes flagged neighborhoods from PSF fits. Under-sampled stars and hot
pixels may be flagged. No interpolation is applied. The QC sharpness metric
is the reciprocal of median fitted FWHM. Axial elongation coherence is the
magnitude of the mean doubled-angle unit vector for fits with ellipticity
at least 0.15. A preferred direction can reflect tracking, optics, or seeing.
