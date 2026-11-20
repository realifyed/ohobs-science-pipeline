# Configure an observatory

Copy [observatory.yaml](../../configs/examples/observatory.yaml) to the repository
root as observatory.yaml. It contains no assumed detector measurements.
[OHOBS-01](../../configs/examples/ohobs-01.yaml) is a separate instrument example.
Run `osp config validate --config observatory.yaml` after editing. Unknown keys
are rejected. The [generated JSON schema](../api/configuration-schema.json)
records every supported field, default, type and numeric bound.

Paths resolve relative to the YAML, including solver files and catalogues.
CLI input/output paths resolve relative to the shell's working directory.

| Settings | Meaning |
| --- | --- |
| node | Observatory identifier written as OBSERVAT; required. |
| raw_dir, calibration_dir | Optional discovery roots; explicit CLI inputs take precedence. |
| work_dir | Registry, products, receipts, jobs database and events root. There is no separate output_dir key. |
| detector.model, readout, full_shape | Descriptive detector identity and full-frame geometry [height, width]; metadata still comes from headers or overrides. |
| detector.pixel_um, output_bits, manufacturer, sensor, cooling | Instrument description; supply only known values. |
| detector.gain_e_per_adu, read_noise_e, saturation, linear_max | Measured physical parameters, not acquisition GAIN codes. Require evidence and characterized_settings. Unknown values stay null. |
| detector.characterized_settings | Bind evidence to camera, readout, gain, offset, bin_x, bin_y, unit, temperature_min_c and temperature_max_c. |
| detector.bad_pixels_yx, hot_pixels_yx, dead_pixels_yx | Measured defect coordinates [row, column]. |
| calibration | Combination method, minimum frames, clipping/bootstrap settings, flat response floor and matching policy. |
| calibration.detector_keys, optical_keys | Additional FITS header names that must match; missing required headers are errors. |
| quality | Detection/fit settings and optional acceptance thresholds. Unset thresholds are not invented instrument specifications. |
| astrometry | Solver selection, pixel-scale bounds (arcsec/pixel), pointing radius, reference and verification thresholds. |
| workers, memory_mib, max_input_mib, worker_timeout_s | Worker count, estimated algorithm memory admission budget, input size limit and worker timeout. Allow extra memory for Python, libraries and solver indexes. |
| overrides | Explicit normalized metadata assertions, recorded along with observed values. |
| synthetic_test | False for observational work. True only in a separate synthetic workspace. Origins cannot be mixed. |

Gain code, offset, binning, exposure, temperature and filter are acquisition
metadata, not new top-level YAML fields. See [ingestion](fits-ingestion.md) for
header aliases and all supported overrides. Configuring detector.model alone
does not fill missing acquisition headers. Missing ROI origins may be inferred
only for matching configured full geometry at 1x1 binning.

There is no telescope, focal_length or filter_aliases configuration section.
TELESCOP in the input header is preserved. Encode optical configuration identity
in OPTICID (or a justified `overrides.optics`) and optionally optical_keys.
Use a measured focal length and pixel pitch to estimate a pixel-scale search
range externally; set both astrometry.scale_min and scale_max. Do not insert
nominal values as measured detector evidence. Normalize filter labels at
acquisition or use a documented per-run `overrides.filter`; a global override
would incorrectly collapse a mixed-filter batch.

Nonzero temperature tolerance requires calibration.temperature_evidence.
The bias-only path requires bias_only_max_exposure_s and bias_only_evidence;
the default uses exposure-matched darks. Mean needs at least five frames by
default; median/clipped_mean require at least twelve. Keep science and flat
offset references independent. Read [calibration](calibration.md).

The [astrometry configuration reference](../configuration.md) documents online,
Gaia and optional independent photon expectation settings. Never store an API
key in YAML. Validate physical measurements against the original characterization
record, not merely against schema acceptance.
