# First observational reduction

Use a working directory with observatory.yaml, observations/light.fits and
calibration/{dark,flat-dark,flat}/. Copy the generic YAML to this root and
configure it for the actual acquisition settings. Separate flat sets by filter
and exposure. Here each directory contains exactly five compatible frames
named 01.fits through 05.fits; replace these explicit filenames with yours.
Explicit paths work in both PowerShell and Bash without shell glob assumptions.

```sh
osp config validate --config observatory.yaml
osp fits inspect observations/light.fits --config observatory.yaml
osp masters build --config observatory.yaml --kind DARK calibration/dark/01.fits calibration/dark/02.fits calibration/dark/03.fits calibration/dark/04.fits calibration/dark/05.fits
osp masters build --config observatory.yaml --kind FLAT_DARK calibration/flat-dark/01.fits calibration/flat-dark/02.fits calibration/flat-dark/03.fits calibration/flat-dark/04.fits calibration/flat-dark/05.fits
```

Save the returned IDs. Replace FLAT_DARK_ID below with the short reference's ID:

```sh
osp masters build --config observatory.yaml --kind FLAT --flat-dark FLAT_DARK_ID calibration/flat/01.fits calibration/flat/02.fits calibration/flat/03.fits calibration/flat/04.fits calibration/flat/05.fits
osp masters list --config observatory.yaml
osp reduce observations/light.fits --config observatory.yaml --dry-run
osp reduce observations/light.fits --config observatory.yaml
```

Automatic selection requires exactly one compatible master of each kind. Pass
`--dark DARK_ID --flat FLAT_ID` to choose explicitly. A dry run checks planning
and compatibility, not successful science processing. The reduction JSON returns
`path`, `id` and `state`. Replace PRODUCT below with that path:

```sh
osp validate PRODUCT
osp qc PRODUCT --config observatory.yaml
osp report --product PRODUCT --html exposure.html
osp batch --input observations --config observatory.yaml
```

No raw file is overwritten. Products live under work_dir/products/ID. Read
[calibration](../user-guide/calibration.md), [products](../user-guide/data-products.md)
and [astrometry](../user-guide/astrometry.md) before interpreting scientific status.
These input names describe your supplied observations; the automated fixture
workflow exercises equivalent commands without requiring real data.
