# Calibration masters and selection

Use [first reduction](../getting-started/first-reduction.md) for complete CLI
commands. `masters build` accepts explicit FITS paths or discovers the configured
calibration_dir if no paths are supplied. A discovered directory must contain a
compatible homogeneous set, not a mixture of darks, flats and lights.

The registry stores masters under work_dir/masters/ID with master.fits and
manifest.json. Inputs, configuration and software participate in identities;
checksums and transitive flat-dark lineage are checked. `masters list` returns
IDs, kinds and statistics; `masters inspect ID` returns the full manifest.

Detector identity includes camera, model, readout, gain code, offset, binning,
ROI, units, shape and configured extra detector headers. Darks and flat-darks
must match exposure and temperature policy to their target exposures. Science
flat selection matches detector identity, filter, optical identity and optical_keys;
flat exposure need not equal science exposure. Each flat retains its own matched
flat-dark lineage. Origin and synthetic generator identity must
agree. There is no generic dark scaling or arbitrary nearest-master selection.
Ambiguity fails rather than silently choosing a candidate.

Flats are offset-corrected with their matched flat-dark and normalized. Mean is
the default; median and clipped mean use bootstrap variance with at least twelve
frames. The default minimum for mean is five. Low-response and invalid support
are masked. Calibration computes (raw - dark) / normalized_flat. The matched
dark already contains bias; do not subtract bias again.

An evidence-gated bias-only mode uses zero-exposure independent references for
science and flats. It requires a measured negligible-dark exposure limit and
evidence. Science and flat reference input sets must be disjoint because their
covariance is not propagated. Missing/incompatible masters prevent publication;
missing physical noise information can instead yield PARTIAL products.

See [methodology](../science/calibration-methodology.md) and
[scientific limitations](../science/assumptions-and-limitations.md).
