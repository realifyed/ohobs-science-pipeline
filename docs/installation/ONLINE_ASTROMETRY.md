# Nova and local ANSVR

OSP can submit selected centroids to the official Astrometry.net Nova API
without ANSVR installed. ANSVR local mode works offline. Both use the same
geometric WCS checks and local Gaia comparison.

## Rotate and load the key

Sign in to [Astrometry.net](https://nova.astrometry.net/) and open your
profile to locate your API key. Treat any key previously shared in conversation
as exposed. Ask Astrometry.net support to revoke and replace it if the profile
does not provide a rotation control. Enter the replacement only into your
local terminal or credential manager.

In PowerShell 7, read the replacement into the current process environment.
Remove the variable when finished. OSP looks only at the process environment;
it does not read dotenv files.

```powershell
$secret = Read-Host 'Rotated Astrometry.net API key' -AsSecureString
$env:OSP_ASTROMETRY_API_KEY = [Net.NetworkCredential]::new('', $secret).Password
Remove-Variable secret
osp astrometry probe --backend online --config configs/ohobs-01.example.yaml
Remove-Item Env:OSP_ASTROMETRY_API_KEY
```

An `AVAILABLE` probe result confirms Nova login. Probing never uploads a
field. DNS, TLS, HTTP, and authentication have distinct diagnostics.

## Submit a field

Before using an actual exposure, review the visibility and data-sharing policy.
Nova receives a subset of brightness-ordered centroids by default. Positions,
image size and optional pointing hints can reveal a field. Non-public
visibility requests do not guarantee that all server-side job metadata remain
private. Do not share submission IDs or receipts outside the intended audience.
The API is a third-party service and may retain submissions. API keys and
session tokens remain in process memory and are excluded from receipts.

```powershell
osp astrometry solve 'observation.fits' --backend online --allow-online `
  --config configs/ohobs-01.example.yaml --output nova-first
```

For an explicitly authorized image solve, set `online.upload_mode: image`
or `image_fallback` and add `--allow-image-upload` as well as `--allow-online`.
The upload contains a single float32 pixel plane with unchanged dimensions and
axis order. OSP strips original FITS headers and other HDUs from that upload.
Whole-plane solves can yield diagnostic WCS and Gaia residuals. They cannot meet
OSP's independent image-source holdout requirement because Nova received all
pixels. Image fallback runs only after insufficient fitting sources or a
terminal Nova solve failure.

## Local and automatic modes

```powershell
osp astrometry probe --backend local --config configs/ohobs-01.example.yaml
osp astrometry solve 'observation.fits' --backend local `
  --config configs/ohobs-01.example.yaml --output local-first
```

Start ANSVR from the Windows Start menu if needed. The default is
`http://127.0.0.1:8080`. Set `astrometry.ansvr_url` for a different local port;
IPv4 and IPv6 loopback are supported. No Nova credential is needed. The
[Windows ANSVR guide](../commissioning/ANSVR-HTTP-VALIDATION.md) covers the
observatory machine and its existing service.

Select `auto` and set `astrometry.fallback_enabled: true` to permit fallback
after a local solve failure. Also provide `--allow-online`, or explicitly set
`online.authorize_upload: true` for unattended jobs. A locally solved but
unverified WCS remains a local candidate. It does not trigger online disclosure.

## Resume and verify

The error or result includes a local receipt ID when a submission may exist.
`astrometry status RECEIPT_ID --wait --config CONFIG` resumes polling without
uploading again. A solve timeout leaves the candidate pending. Use
`--cancel` to interrupt OSP's local wait. Nova has no documented public
cancel API, so Nova can continue processing. Resume clears the local cancel
marker. If a connection dropped before acknowledgement, inspect your Nova
account's submission history and use `--attach SUBMISSION_ID` only when you
can identify the exact job. Manually attached WCS is diagnostic. If you
confirm that no submission was created, `--abandon` releases the ambiguous
receipt's queue slot while retaining the no-replay record.

```powershell
osp astrometry status RECEIPT_ID --wait --config configs/ohobs-01.example.yaml
osp astrometry verify 'observation.fits' --wcs nova-first/candidate.wcs `
  --solve-report nova-first/validation.json --config configs/ohobs-01.example.yaml
```

After resumption, rerun the original solve with a fresh output directory to
apply shared geometry and Gaia verification. The saved WCS can be reused.
For batch products already published as PARTIAL, use a new `--revision` to
create new products while preserving the prior evidence and reusing receipts.
The standalone verify command performs no network requests. It checks the
prior report's WCS checksum and extraction digest before allowing a holdout
claim. The configured reference ECSV must cover the actual field. Independent
catalogue evidence must apply to the backend that actually solved it. Nova's
index provenance is not established by a local 2MASS index manifest.

See the [official Nova API](https://astrometry.net/doc/net/api.html),
[Astroquery interface](https://docs.astropy.org/projects/astroquery/en/stable/astrometry_net/astrometry_net.html),
and [ANSVR documentation](https://adgsoftware.com/ansvr/).
