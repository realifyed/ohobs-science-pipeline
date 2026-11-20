# FITS discovery and metadata

`osp fits inspect observations/light.fits --config observatory.yaml` returns a
JSON manifest including SHA-256, shape, HDU, normalized metadata, metadata
sources, time fields, original header and raw WCS status. Inspection is read-only.
Batch discovery recursively finds .fits, .fit and .fts case-insensitively,
sorts entries and skips file and directory symlinks. Keep files still being
acquired or copied outside the input tree.

One uncompressed two-dimensional image plane is supported. Input checks include
FITS structure, scaling, available checksums and file-change detection.
Do not interpret successful inspection as calibration compatibility.

| Normalized override | FITS aliases, in priority order |
| --- | --- |
| camera | CAMERAID, INSTRUME |
| model | INSTRUME |
| readout | READOUTM, READMODE |
| gain, offset | GAIN, OFFSET |
| bin_x, bin_y | XBINNING/CCDXBIN, YBINNING/CCDYBIN |
| roi_x, roi_y | XORGSUBF, YORGSUBF |
| temp | CCD-TEMP, SENSORT |
| exposure | EXPTIME, EXPOSURE |
| filter, optics, unit | FILTER, OPTICID, BUNIT |
| kind | IMAGETYP, OBSTYPE |

Supported kind aliases normalize OBJECT/SCIENCE to LIGHT, ZERO to BIAS, and
DARK_FLAT/DARKFLAT/FLATDARK to FLAT_DARK. Units normalize to adu or electron.
Conflicting exposure aliases are rejected. Calibration needs full acquisition
settings and appropriate temperature, exposure, optical and timing metadata.
Explicit overrides take precedence and retain observed header values in
provenance. They are operator assertions, not inferred measurements.
