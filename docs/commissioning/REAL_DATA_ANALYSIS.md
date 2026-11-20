# OHOBS observational commissioning

**VERIFIED inventory**. The 98-row inventory (private acquisition record; not distributed) enumerates byte SHA-256, detector and optical cards, UTC start and average, FITS storage scaling, pointing, code extrema, median and count at 65520. All hashes are distinct. Data contain 60 flats and 38 light files, and zero dark, bias, or flat-dark files. No raw file contained a celestial WCS. The UT start interval is 2026-05-03 20:28:26.937 through 22:34:42.571 (2026-05-04 01:58:26.937 through 04:04:42.571 IST).

| Group | EXPTIME | CCD-TEMP | Files | Count of pixels at 65520 | Median-code span |
| --- | ---: | ---: | ---: | ---: | --- |
| Hα flat | 3.75875 s | 18.8 °C | 30 | 40 | 17776–55696 |
| O flat | 5.02945 s | 18.8 °C | 30 | 25,147,401 | 20368–65520 |
| Hα light | 120 s | 18.9 °C | 23 | 173 | 2240–2592 |
| Hα light | 120 s | 19.0 °C | 6 | 43 | 2256–2496 |
| O light | 120 s | 18.9 °C | 7 | 63 | 2272–2384 |
| O light | 120 s | 19.0 °C | 2 | 18 | 2240–2320 |

**FAILED delivered O-flat set as an unfiltered master input**. Three O flats ending in 0002, 0013 and 0025 have 99.16%, 99.99999% and 100% of pixels at 65520, respectively. The three frames account for virtually the entire pile-up. The O set also has wide illumination drift, and the Hα span is above a factor of three. An exposure with nearly all pixels at one code cannot measure spatial response. Remove those three from any candidate set and prefer fresh, stable O flats. Screen the remaining O and Hα exposures for reliable signal and stable flat ratios against measured linearity before making a master. Sparse top-code pixels in science or flats can be defects or clipped targets. Treat them as candidates for masking pending characterization. The physical threshold is UNVERIFIED.

**VERIFIED metadata**. All inputs have the identical QHYminiCam8M camera ID, no EGAIN, no BUNIT, no optical ID, gain and offset settings 30, Full Resolution, and reported 0 °C set point. The actual reported sensor values above are used for matching. Standard unsigned scaling yields 16-count code spacing in 96 files. The exceptions are a two-code flat and the single-code flat. FITS storage width and code spacing cannot establish electrons per ADU. Differences between DATE and MJD are at most 1.007 ms. DATE-AVG minus nominal start-plus-half-exposure is −0.593 to −0.571 s for lights, and −0.099 to −0.074 s for flats. A timing bias against true shutter times remains UNVERIFIED. Header RA/Dec are pointing hints at best. The two object-name groups have different pointing ranges; use individual pointings and independent solutions rather than a single field of reference stars.

**FAILED real reduction attempt**. The original configuration stops on absent unit and optical ID. A dry run with explicit provisional metadata proceeds to calibration matching and finds zero science darks. All 38 lights are blocked, and no flat has the required flat-dark. No real SCI/ERR or astrometric residual has been produced. The local solve-field executable is absent and the WSL inventory call failed with access denied. See real-attempt.log (local commissioning record; not distributed).

## Reproduce the inventory and commissioning

1. From the repository with OSP installed, run `python benchmarks/real_inventory.py Test-data docs/commissioning/OHOBS_FITS_INVENTORY.csv`. Preserve a copy of the explicit plan in [CAMERA_CHARACTERIZATION_REQUIREMENTS.md](CAMERA_CHARACTERIZATION_REQUIREMENTS.md). Capture and retain the independent master and validation sets.
2. Make a copy of `configs/ohobs-01.example.yaml` as `configs/commissioning.yaml`. Set the work directory outside all raw directories. Verify unit and optical correspondence with acquisition evidence before adding `overrides: {unit: adu, optics: AS_BUILT_CONFIGURATION_ID}`. Use the exact temperature default until supported by held-out data. Include measured gain and characterized settings only after the reported calibration tests. Keep all master builds homogeneous. For each dark duration and actual sensor bin, run `osp masters build --config configs/commissioning.yaml --kind DARK <matching paths>`. N.I.N.A. may label short capped frames DARK; build each group with `--kind FLAT_DARK`. Build one screened FLAT group per filter with `--flat-dark <matching ID>`. Check every result and withhold controls.
3. On a Linux host with Astrometry.net, run `solve-field --help` and install indexes covering the expected quad scales for the actual footprint. For catalogue independence use the Astrometry.net 4200-series built from 2MASS rather than a Gaia-derived index. For an initial index and scale search, the 2.9 μm pixels and header focal length 560 mm imply about 1.07 arcsec/pixel and a 1.14° × 0.65° field; these are nominal planning estimates. Use the [index guide](https://data.astrometry.net/) for coverage at each pointing. Save backend configuration with only the chosen indexes, and record index filenames and hashes; record solver version. Confirm it is discoverable with `command -v solve-field`. Avoid introducing a restrictive pointing prior until the header quality is verified.
4. For each light's actual footprint, use Gaia Archive TAP with the query below, initially centered on its own pointing. A 1° radius is a starting search given the nominal dimensions. If a diagnostic candidate lies outside, re-center on the candidate and ensure the full field is covered. Export to ECSV using `Table.read("gaia.csv", format="ascii.csv").write("gaia.ecsv", format="ascii.ecsv")`. Verify CSV columns and units. Record catalogue query, release, magnitude cut, footprint, solution independence and proper-motion coverage. Choose and document the match radius and science residual requirement before acceptance. Astroquery can retrieve the same TAP result but introduces a network dependency.
5. Set `astrometry.executable`, `astrometry.backend_config`, `astrometry.catalogue` and `astrometry.catalogue_independence_evidence` in YAML. Set the independently chosen `max_rms_arcsec`; the example leaves it unset. Apply the appropriate reference to each exposure as the files cover multiple pointings. Run `osp reduce "<light.fits>" --config configs/commissioning.yaml --dark <ID> --flat <ID> --dry-run`, then rerun without dry-run if selection is sound. Run `osp validate "<product>/science.fits"`. Retain `astrometry.json` and its solver logs.
6. For each field record held-out candidates, mutual matches, unmatched, outliers, median, robust scatter and pre/post-clipping RMS in angular units, and plot east/north offsets against detector coordinates. Check spatial coverage and repeated-observation star residuals. Compare withheld calibration frames, backgrounds and aperture fluxes as well as agreement in WCS. Only statuses supported by actual results should be reported as VERIFIED.

```sql
SELECT source_id, ra, dec, pmra, pmdec, ref_epoch, ruwe, duplicated_source
FROM gaiadr3.gaia_source
WHERE 1=CONTAINS(
  POINT('ICRS',ra,dec),
  CIRCLE('ICRS', <light RA in degrees>, <light DEC in degrees>, 1.0))
AND pmra IS NOT NULL AND pmdec IS NOT NULL AND phot_g_mean_mag < 18
```

The magnitude selection is for a first commissioning trial. Review completeness and the density of chance matches before adopting it. Use [Gaia schema](https://gea.esac.esa.int/archive/documentation/GEDR3/Gaia_archive/chap_datamodel/sec_dm_main_tables/ssec_dm_gaia_source.html), [FITS WCS](https://fits.gsfc.nasa.gov/fits_wcs.html), and the [Astrometry.net manual](https://astrometry.net/doc/readme.html).
