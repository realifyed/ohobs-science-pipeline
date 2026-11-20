# Astrometry configuration

```yaml
astrometry:
  backend: auto
  ansvr_url: http://127.0.0.1:8080
  timeout_s: 120
  fallback_enabled: false
  scale_min: 0.95
  scale_max: 1.19
  online:
    endpoint: https://nova.astrometry.net
    timeout_s: 300
    request_timeout_s: 20
    poll_s: 2
    retries: 3
    upload_mode: source_list
    publicly_visible: false
    authorize_upload: false
    authorize_image_upload: false
    max_concurrent_jobs: 2
    max_sources: 300
    max_image_mib: 48
```

`backend` accepts `local`, `online`, and `auto`. The legacy names
`ansvr_http`, `ansvr`, and `astrometry_net` remain valid. ANSVR defaults to
loopback. Set `allow_private_ansvr: true` only for a trusted private-LAN
ANSVR IP when you intend to send centroids over that network in cleartext.
Online is restricted to the official Nova HTTPS origin.
Existing catalogue, pointing and WCS acceptance settings still apply.

`astrometry.gaia.enabled` automatically requests a Gaia DR3 catalogue for
the candidate WCS if no local `astrometry.catalogue` is supplied. The default
`gaia.allow_network: false` permits cache hits only. Enable networking
explicitly to send the rounded sky center, cone radius, and catalogue filters
to ESA over HTTPS. Only those query parameters are sent. The cache defaults
to `WORK_DIR/gaia-cache`. Inspect each result's catalogue query and digest
in the astrometry receipt. A missing reference keeps the candidate
unverified, with science and QC preserved. A change in owner-specified
independence evidence still requires deliberate reprocessing.
`online.catalogue_independence_evidence` is distinct from local evidence.

`fallback_enabled` governs AUTO. Upload authorization governs both ONLINE
and the AUTO online branch. The queue limits unresolved submissions and
ambiguous uploads per workspace. Keep one workspace and a consistent
concurrency limit for an unattended batch. Acknowledged jobs are never
uploaded again automatically. Relative paths resolve from the YAML.

Current-process credentials use only `OSP_ASTROMETRY_API_KEY`. Upload permission,
selected backend and non-secret settings enter run identities. Credentials
do not. CLI overrides are passed through batch workers and recorded with
the batch definition.

An optional top-level `photon_expectation` FITS and nonempty
`photon_expectation_evidence` enable observation-specific propagation.
The model must be a single plane in the raw light's units and detector
coordinates, with `OBS_ID` equal to the raw SHA-256 and `OSSIGNAL` set to
`INDEPENDENT`. Supply expected light plus sky above dark using data
independent of this exposure's pixel noise. Document the acquisition and
model in the evidence field. The model digest enters the product identity.
The science pixels retain the measured dark-subtracted signal.

Top-level `synthetic_test: true` designates a synthetic-only test workspace.
The default is `false`, which admits observational inputs. Masters and
science inputs must agree on data origin and synthetic generator identity.
See the [data origin policy](installation/SIMULATION-MIGRATION.md#data-origin-policy).
