# Instrument and acquisition

QHY lists the Sony IMX585, 3856 × 2180 total pixels, 2.9 µm pitch, dual 12-bit ADC with 16-bit output and dual-stage TEC for the miniCAM8. The supplied frames identify the monochrome QHYminiCam8M, Full Resolution, gain/offset settings 30/30, binning 1×1. Signed FITS storage with BITPIX 16 and BZERO 32768 represents unsigned physical values. The guide camera has a different sensor and is outside the science profile.

| Parameter | Node 01 evidence |
| --- | --- |
| Actual CCD-TEMP | Flats 18.8 °C, lights 18.9 or 19.0 °C. SET-TEMP is the set point. |
| Gain conversion, read noise, saturation, linearity and ADC code mapping | **UNVERIFIED** at these settings. Manufacturer HDR figures and general ranges cannot establish them. |
| Dark/glow, temperature tolerance and temporal stability | **UNVERIFIED**. No dark or flat-dark frames supplied. |
| Optics | Askar 80ED with 1× field flattener per specification. Assign an optical identity for the actual run. |
| Exposure timing | Supplied UTC DATE and MJD variants agree within about 1.01 ms. Clock accuracy, latency and site elevation accuracy remain **UNVERIFIED**. |

DATE-OBS is used as exposure start and DATE-AVG as N.I.N.A.'s averaged midpoint where present. FITS TIMESYS takes precedence over the UTC default. OSP records DATE-minus-MJD differences and rejects disagreements above 2 ms. This representation tolerance is independent of timing accuracy. OSP derives missing endpoints and midpoint from exposure duration. The original cards remain in provenance. Barycentric corrections require independently verified timing, location and target.

For a paired photon-transfer sequence, collect matched independent flat and dark pairs under controlled uniform illumination at each exposure level. Half the variance of a pair difference estimates temporal variance while cancelling fixed spatial response. Subtract dark-pair variance from flat-pair variance, then fit the linear interval against dark-subtracted net signal. The reciprocal slope is electrons per ADU. Use an independent zero-exposure matched bias pair for noise near zero exposure. Check dose stability and inspect pair differences for row and common-mode correlations. Repeat at actual temperatures and detector settings. Record saturation and linearity against measured response and a chosen tolerance. Dark means contain the offset and cannot by themselves measure isolated dark current.

`osp camera characterize sequence.json --config CONFIG` accepts a JSON object with a `levels` array of at least four entries. Each entry has `flat` and `dark` arrays containing two paths each and a Boolean `fit`. Select at least three fit levels. An optional `bias_pair` contains two paths. Output includes the regression standard error, linearity residuals, dark observations and input identities. Saturation requires separate evidence.
