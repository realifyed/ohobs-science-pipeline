# Scientific references

| Reference | Application |
| --- | --- |
| [QHYCCD miniCAM8 specifications](https://www.qhyccd.com/minicam8-imx585/) | Sensor, pixel pitch, geometry, readout format and cooling |
| [N.I.N.A. FITS header reference](https://nighttime-imaging.eu/docs/develop/site/advanced/file_formats/fits/) | Acquisition metadata |
| [IAU FITS Standard 4.0](https://fits.gsfc.nasa.gov/fits_standard.html) and [FITS WCS conventions](https://fits.gsfc.nasa.gov/fits_wcs.html) | Physical values, undefined values, time, HDUs and celestial transformation |
| [Astropy FITS image data](https://docs.astropy.org/en/stable/io/fits/usage/image.html) | Stored values, scaling and memory-mapped access |
| [Astropy CCD guide on image combination](https://www.astropy.org/ccd-reduction-and-photometry-guide/v/2.0.0/notebooks/01-06-Image-combination.html) and [dark artifacts](https://www.astropy.org/ccd-reduction-and-photometry-guide/notebooks/03-02-Real-dark-current-noise-and-other-artifacts.html) | Replicates, combination, robust estimators, offset and dark patterns |
| [EMVA 1288 Release 4.0 Linear](https://www.emva.org/wp-content/uploads/EMVA1288Linear_4.0Release.pdf) | Paired variance, photon transfer and response |
| [SciPy least squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html) | Bounded Gaussian fits and fit Jacobian |
| [Photutils point-like source detection](https://photutils.readthedocs.io/en/stable/user_guide/detection.html) | Convolved images for candidate selection. OSP uses its own optional mask-normalized Gaussian pass and fits on the original residual image. |
| [Astrometry.net user guide](https://astrometry.net/doc/readme.html) | XY-list solving, indexes and local backend |
| [Astrometry.net Nova API](https://astrometry.net/doc/net/api.html) and [Astroquery Astrometry.net](https://docs.astropy.org/projects/astroquery/en/stable/astrometry_net/astrometry_net.html) | Online submission, acknowledgement, job polling and WCS retrieval |
| [Astropy calibration overview](https://www.astropy.org/ccd-reduction-and-photometry-guide/v/2.0.0/notebooks/01-05-Calibration-overview.html) and [bias in matched darks](https://www.astropy.org/ccd-reduction-and-photometry-guide/notebooks/03-04-Handling-overscan-and-bias-for-dark-frames.html) | Additive offset, thermal signal, multiplicative response and separate bias path |
| [Photutils pixel conventions](https://docs.astropy.org/projects/photutils/en/stable/getting_started/pixel_conventions.html) | Zero-based truth coordinates and one-based FITS WCS |
| [ANSVR developer notes](https://gist.github.com/agalasso/684419e13a00dedd5312d46009482564) and [Astrometry.net index provenance](https://data.astrometry.net/) | Direct Windows solver invocation and selection of 2MASS-derived indexes for independent Gaia assessment |
| [Gaia DR3 definitions](https://irsa.ipac.caltech.edu/data/Gaia/dr3/gaia_dr3_source_colDescriptions.html) and [ESA Gaia schema](https://gea.esac.esa.int/archive/documentation/GEDR3/Gaia_archive/chap_datamodel/sec_dm_main_tables/ssec_dm_gaia_source.html) | Reference epochs, ICRS and proper-motion convention |
