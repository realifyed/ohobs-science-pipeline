# Astrometry backends and verification

| backend | Integration | Verification status here |
| --- | --- | --- |
| astrometry_net | Native solve-field executable and local indexes; intended Linux route | Adapter and offline regressions; live Linux/index solving unavailable |
| ansvr | Windows ANSVR bundled Cygwin executable via ansvr_root | Historical Windows commissioning; not re-commissioned in this audit |
| ansvr_http / local | ANSVR-compatible HTTP service, loopback by default | Offline protocol tests; live service not required by CI |
| online | Official Nova HTTPS API | Offline tests; no live credential/service claim |
| auto | Local HTTP first, optional authorized Nova fallback | Offline routing/recovery tests; not a native solve-field fallback |

## Native Linux solver

Install Astrometry.net and index files separately. Upstream explains
[installation and field-scale index selection](https://astrometry.net/doc/readme.html).
Indexes must cover your field and angular scale; software installation alone
is insufficient. In observatory.yaml:

```yaml
astrometry:
  backend: astrometry_net
  executable: solve-field
  backend_config: solver/astrometry.cfg
  timeout_s: 120
```

Use a real solver configuration file in that location, with index paths valid
on the solver host. Omit backend_config to use the external solver's default.
executable is a PATH lookup name or a usable executable path; use an absolute
path if it is outside PATH. OSP passes source tables, image dimensions and any
configured scale/pointing bounds. No raw image upload is needed for local solving.
Native Linux operation is pending execution with real indexes.

## Windows ANSVR

Use the [Windows commissioning guide](../commissioning/ANSVR-WINDOWS.md) for
ANSVR setup. For service mode, replace the astrometry block with:

```yaml
astrometry:
  backend: local
  ansvr_url: http://127.0.0.1:8080
```

Use the actual port from ANSVR settings. Do not retain executable/backend_config
with local/auto. The ansvr backend instead requires ansvr_root and its bundled
Cygwin tools. Private LAN HTTP requires explicit allow_private_ansvr and sends
centroids unencrypted. ANSVR's Windows installer does not run natively on Linux.

## Online Nova

Create a Nova account and obtain an API key through the
[official API service](https://astrometry.net/doc/net/api.html). OSP accepts only
the official HTTPS endpoint. Keep the key in the current process environment;
dotenv files are not loaded. Never commit it to YAML, shell scripts or receipts.

PowerShell:

```powershell
$secret = Read-Host 'Astrometry.net API key' -AsSecureString
$env:OSP_ASTROMETRY_API_KEY = [Net.NetworkCredential]::new('', $secret).Password
Remove-Variable secret
```

Bash:

```bash
read -r -s -p 'Astrometry.net API key: ' OSP_ASTROMETRY_API_KEY
export OSP_ASTROMETRY_API_KEY
printf '\n'
```

After the session, remove it with `Remove-Item Env:OSP_ASTROMETRY_API_KEY` in
PowerShell or `unset OSP_ASTROMETRY_API_KEY` in Bash.

```sh
osp astrometry probe --backend online --config observatory.yaml
osp astrometry solve observations/light.fits --backend online --allow-online --config observatory.yaml --output nova-result
```

Probing logs in without uploading. Default source_list mode submits ranked
centroids, dimensions and optional hints, which can identify the observed field.
Nonpublic visibility is a request, not a confidentiality guarantee. Image or
image_fallback mode additionally requires --allow-image-upload and uploads a
header-stripped float32 plane. Whole-image submission cannot satisfy independent
source holdout. Review third-party retention/privacy before authorization.

Defaults: overall online timeout 300 s, request timeout 20 s, polling 2 s,
three retries and at most two unresolved jobs per workspace. These are OSP
limits, not a guaranteed service quota. Respect server rate-limit responses;
network availability and service turnaround are outside OSP's control.
AUTO also requires fallback_enabled: true and upload authorization. A locally
solved but unverified candidate does not trigger disclosure via fallback.

## Candidate acceptance and recovery

```sh
osp astrometry probe --config observatory.yaml
osp astrometry solve observations/light.fits --config observatory.yaml --output local-result --verify
osp astrometry verify observations/light.fits --wcs local-result/candidate.wcs --solve-report local-result/validation.json --config observatory.yaml
```

Output directories must be new. solve_status and verification status are distinct.
Without --verify a returned candidate can exit zero even when unverified.
Independent verification requires a configured reference, catalogue-independence
evidence and suitable RMS/match/coverage criteria. One in three detected sources
is held out. Candidate WCS must pass geometric and epoch-aware catalogue checks.
Only VERIFIED WCS enters SCI. No solver implies no accepted astrometry, not loss
of calibrated pixels. [Limitations](../science/assumptions-and-limitations.md)
describe proper-motion assumptions and omitted effects.

Supply a local Gaia DR3 ECSV with source_id, ra, dec, pmra, pmdec, ref_epoch
(degrees, mas/year, TCB Julian years), optionally ruwe and duplicated_source.
Alternatively enable astrometry.gaia.enabled; network access additionally needs
gaia.allow_network. Cache queries and digests are recorded. The standalone
verify command can retrieve a catalogue when Gaia is enabled and networking
is explicitly allowed. For offline verification supply a local catalogue or
keep gaia.allow_network false and prepare the cache first.

Online receipts allow `osp astrometry status RECEIPT_ID --wait --config observatory.yaml`
without another upload. --cancel stops local polling, not server processing.
After an ambiguous upload inspect Nova history before --attach or --abandon.
See [online operations](../installation/ONLINE_ASTROMETRY.md) and
[configuration details](../configuration.md).
