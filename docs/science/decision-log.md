# Scientific decisions

| Decision | Reason | Evidence |
| --- | --- | --- |
| Use offset-bearing matched darks | Avoid duplicate offset removal and unmodeled dark scaling | End-to-end synthetic offset and exposure-dependent dark case |
| Require exact physical settings and explicit temperature evidence | Prevent invalid matching | Rejection tests separate exposure, temperature, mode, gain, ROI and filter |
| Use temporal matched-dark noise and measured gain | Count dark and read variance once | Monte Carlo comparisons in low and bright signal regimes |
| Bootstrap robust estimators | Sample scatter divided by n does not capture clipping or median sampling | Determinism and outlier tests |
| Hold out solver detections | Assess agreement outside the fit | Synthetic epoch, RA wrap, pixel origin and failed WCS cases |
| Publish atomic content-addressed products | Make reuse verifiable and preserve calibrated results after later failures | Failure and job resumption tests |
## a3 commissioning decisions

- ANSVR's bundled Astrometry.net solver takes pixel coordinates from the same
  fitting subset as the native adapter. The held-out detections and separate
  catalogue still govern verification. Direct invocation retains the FITS WCS
  including distortion parameters and avoids dependence on a listening endpoint.
- Three delivered O flats pile up at 65520. An optional screen counts the
  occupancy of each image's maximum usable scaled code during flat construction.
  A limit of 0.99 would reject those three in the raw inventory. This setting is
  a configurable screen for degenerate input. The physical saturation and
  linearity limits still require detector measurements. The screen cannot
  retrospectively qualify already built masters or detect every unsuitable flat.
