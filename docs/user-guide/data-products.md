# Scientific products

Each published product directory under work_dir/products/ID contains science.fits,
provenance.json and stage reports (including qc.json and astrometry.json).
The provenance records the processing definition and file hashes. Preserve the
directory as a unit. `osp validate PRODUCT` checks product structure and integrity;
`osp report --product PRODUCT` inspects the associated evidence.

| HDU | Contents |
| --- | --- |
| PRIMARY | Empty data; schema/version, input digest, master IDs, configuration hash, observation times and stage statuses. |
| SCI | Floating calibrated pixels in raw adu or electron units; accepted celestial WCS appears here. |
| ERR | Square root of propagated marginal variance, in the same units as SCI. NaN denotes unavailable/invalid uncertainty. |
| DQ | uint16 OR-combined flags; DQBIT header cards name the bits. |

Primary status cards include OSPSTATE, ERRSTAT, QCSTAT and WCSSTAT. ERRSTAT is
CONDITIONAL, PARTIAL or UNAVAILABLE; conditional does not mean a complete error
budget. COMPLETE requires evaluated QC, conditional uncertainty and verified
WCS. PARTIAL preserves usable calibration when later stages are unavailable.
FAILED and QUARANTINED indicate processing or ingestion failure respectively.

| Mask | Flag |
| --- | --- |
| 0x0001 | NONFINITE |
| 0x0002 | SATURATED |
| 0x0004 | BAD_PIXEL |
| 0x0008 | HOT_PIXEL |
| 0x0010 | DEAD_PIXEL |
| 0x0020 | FLAT_INVALID |
| 0x0040 | COSMIC_RAY_CANDIDATE |
| 0x0080 | EDGE (reserved) |
| 0x0100 | INTERPOLATED (reserved) |
| 0x0200 | CALIBRATION_SUSPECT |
| 0x0400 | NONLINEAR_RESPONSE |

Fatal flags invalidate SCI/ERR. Reserved bits do not imply interpolation is
implemented. Saturation and nonlinearity require measured evidence. ERR omits
spatial covariance and the full shared flat-normalization uncertainty; read the
[uncertainty model](../science/calibration-methodology.md) before scientific use.
