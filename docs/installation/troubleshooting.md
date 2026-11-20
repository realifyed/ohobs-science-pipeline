# Troubleshooting

| Symptom | Action |
| --- | --- |
| osp not found | Use the environment's Scripts/osp.exe on Windows or bin/osp on Linux; install with that environment's Python. |
| PowerShell refuses activation | Invoke .venv\Scripts\python.exe and osp.exe directly. Activation is optional. |
| Linux venv unavailable | Install your distribution's Python venv component. |
| No scientific dependency wheel | Check Python and CPU architecture; source builds need upstream compilers and libraries. |
| pip index unreachable | Restore network/proxy/TLS access. A prepared wheelhouse permits replay but does not verify fresh dependency resolution. |
| YAML rejects a key | Unknown keys are errors. Use the generated configuration schema; paths resolve from the YAML. |
| Missing or ambiguous master | Compare detector settings, geometry, exposure, temperature, filter and origin. Build matching masters; use returned IDs explicitly if needed. |
| ADU ERR unavailable | Supply measured gain with evidence for the exact operating settings. Do not substitute nominal values. |
| Native solver cannot launch | Check solve-field lookup and Linux executable permissions; select astrometry_net. local means HTTP. |
| ANSVR connection refused | Start ANSVR on Windows and use its configured loopback port. |
| Help probe passes but solve fails | Check indexes, scale and timeouts. A launch probe does not test indexed solving. |
| WCS unverified | Inspect catalogue availability, independence, held-out matches, coverage and RMS criteria. |
| PARTIAL product | Calibration may succeed while QC, uncertainty or astrometry is incomplete. Inspect reports; use a new revision after fixing the cause. |

Preserve raw data and receipts. Redact private headers, coordinates and paths
before sharing issue reports.
