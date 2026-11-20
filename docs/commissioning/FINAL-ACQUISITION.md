# Final N.I.N.A. acquisition checklist

**BLOCKED** pending capture. These settings come from the supplied 98-file
Lagoon inventory. The frame counts below are commissioning targets.

## Before capture

- Select the same QHYminiCam8M camera. Confirm its camera ID against the raw
  inventory. Use Full Resolution, 1×1 binning, full 3856 × 2180 ROI, gain
  setting 30, offset 30, USB limit 0, and the existing 16-bit FITS acquisition
  mode. Check that the headers retain TOP-DOWN row order. Record camera driver,
  firmware, and N.I.N.A. version. Preserve the originals.
- Use the reported `CCD-TEMP` as the measured matching value. Historical
  files report `SET-TEMP=0` and `CCD-TEMP=18.8–19.0 °C`. Allow temperatures
  to stabilize and review every exposure after acquisition. Preserve the
  acquisition set point and actual temperature as distinct fields.
- Record the actual optical identity. Preserve camera angle, focus approach,
  filters, dust pattern, flattener, and optical train for flats used with old
  lights. If you cannot reproduce a setup or thermal group, capture a new
  matched set of lights and calibration data.

## Capture and separate these groups

| N.I.N.A. acquisition | FITS EXPTIME | Measured CCD-TEMP | Build | Withhold |
| --- | ---: | ---: | ---: | ---: |
| Capped dark for 30 historical H-alpha and O lights | 120.00000 s | 18.9 °C | 32 | 12 |
| Capped dark for eight historical H-alpha and O lights | 120.00000 s | 19.0 °C | 32 | 12 |
| Capped dark for screened H-alpha flats | 3.75875 s | 18.8 °C | 32 | 12 |
| Capped dark for O flats if the historical duration is retained | 5.02945 s | 18.8 °C | 32 | 12 |
| Replacement O flats | Fixed duration inside measured linear range | Stable, recorded | 32 | 12 |
| Replacement H-alpha flats if the historical set fails illumination or optical checks | Fixed duration inside measured linear range | Stable, recorded | 32 | 12 |
| Capped darks for any new flat group | Exact new flat EXPTIME | Same bin as flat group | 32 | 12 |

Use a light-tight cap for darks. Capture withheld groups independently, ideally
in a separate stable acquisition block with the same physical settings. Store
them under separate folders and preserve all header cards. If N.I.N.A. labels
short exposures DARK, build their OSP masters with `--kind FLAT_DARK`.
Check EXPTIME in FITS rather than filenames. Maintain exact matching until
held-out residuals justify a temperature tolerance.

Use stable flat illumination and stay within the measured linear range.
Exclude the nearly uniform historical O flats ending in 0002, 0013 and 0025
from the trial master. Compare ratios between independent flats for pattern
drift before accepting either filter. Inspect medians, percentile ranges,
row and column profiles, dust structure, and bright-code fractions.

## Detector measurements

1. At each tested stable temperature, capture a minimum of 30 capped
   minimum-exposure frames for temporal read-noise analysis. Record the actual
   minimum EXPTIME and do not substitute an assumed zero exposure.
2. Take 12–16 illumination levels from a weak signal through clipping, with
   four independent flat pairs and four matched capped dark pairs per level.
   Repeat the sequence independently. Keep the illumination monitored,
   interleave references, and retain the saturated levels for characterization
   only. Separate the independently measured useful range from the raw
   storage-code ceiling.
3. Estimate gain in electrons per **stored** ADU by paired photon transfer.
   Use paired minimum-exposure data for read noise. Examine quantization,
   drift, row/column covariance, and uniformity of the illuminated region.
   Preserve the raw inputs, paired manifest, uncertainty in fit parameters,
   and the chosen linearity tolerance. The existing `osp camera characterize`
   accepts a `levels` JSON manifest of independent flat/dark pairs and an
   optional `bias_pair`. Keep the measurements and their camera settings with
   the calibration config.

## Evidence to return

- A checksum inventory and an acquisition summary identifying each build and
  withheld group, the optical configuration, and measured temperature range.
- For each withheld dark, biased residual estimates, noise distribution, row
  and column medians, and glow or hot-pixel residual maps. For withheld flats,
  record corrected structure, repeatability, and illumination stability.
- Independent repeat-light aperture variance and covariance for the intended
  use, plus detector gain, read noise, linearity and clipping measurements.
  Set acceptance limits from the intended photometric or astrometric error
  budget before reviewing the residuals.

[N.I.N.A. FITS metadata](https://nighttime-imaging.eu/docs/develop/site/advanced/file_formats/fits/)
and [EMVA 1288 Linear](https://www.emva.org/wp-content/uploads/EMVA1288Linear_4.0Release.pdf)
describe the acquisition and photon-transfer measurements.
