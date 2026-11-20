# Calibration and uncertainty model

The matched-dark correction is S = (R - D) / F, where F is the normalized
offset-corrected flat. D includes electronic offset and dark signal at the
science exposure and operating settings. Flat-darks correct flat exposures at
their own duration. Bias-only correction is enabled only by measured negligible
dark evidence and independent zero-exposure references.

For ADU data with measured gain g, the default first-order marginal variance is

V(S) = [max(R-D, 0)/g + T + V(D) + S² V(F)] / F².

T estimates one exposure's read plus dark-shot variance from temporal dark
samples. Electron-unit inputs use gain one. A separately evidenced independent
expected photon signal can replace the observed plug-in signal in the photon
term and flat derivative. The calibrated numerator remains observed.

This model assumes independent science and offset/flat references. Shared input
sets are rejected. Normalization is treated conditionally; full spatial
covariance, calibration drift, systematics and independent-expectation model
uncertainty are not propagated. At low signal, clipping the plug-in photon
estimate biases variance. Unknown ADU gain leaves ERR unavailable rather than
inventing a noise model. ERR is sqrt(variance), not inverse variance.

The numerical algorithms and regression fixtures are unchanged by repository
documentation work. See [assumptions](assumptions-and-limitations.md),
[historical uncertainty evidence](../validation/uncertainty-commissioning-a4.md)
and [RC1 experiments](../validation/release-rc1.md). Synthetic validation does
not substitute for detector characterization or real photometric validation.
