# Performance, memory and recovery

**PARTIALLY VERIFIED scaling.** Windows 11 build 26300, x86-64 AMD Family 25, 12 logical CPUs, Python 3.14.7, NumPy 2.3.4, SciPy 1.18.1, Astropy 7.2.0 and psutil 6.0.0. Batch trials use distinct 128 × 128 synthetic light files, five synthetic inputs per master, one BLAS thread per worker and a 4096 MiB aggregate admission budget. Results use OSP 0.1.0a2. RSS sums simultaneous parent and descendant working sets at 50 ms intervals. This can double-count shared pages and miss instantaneous peaks. Rows reflect single observed runs with other workstation activity present. No solver was installed, so each completed reduction produced a PARTIAL product.

| Exposures | Workers | Batch wall time | Exposures/s | Parent peak RSS | Sampled tree peak RSS | No-op recovery |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 3.25 s | 0.308 | 83.5 MiB | 215.0 MiB | 0.024 s |
| 10 | 1 | 33.04 s | 0.303 | 84.0 MiB | 215.8 MiB | 0.031 s |
| 10 | 2 | 17.86 s | 0.560 | 84.1 MiB | 347.1 MiB | 0.034 s |
| 10 | 4 | 11.63 s | 0.860 | 85.1 MiB | 611.8 MiB | 0.037 s |
| 100 | 2 | 173.34 s | 0.577 | 84.9 MiB | 349.2 MiB | 0.039 s |
| 200 | 2 | 341.26 s | 0.586 | 85.4 MiB | 349.8 MiB | 0.026 s |

The 2-worker sampled parent peak increased 1.3 MiB from 10 to 200 files. Its post-run RSS for those cases was 83.9, 84.3 and 86.0 MiB respectively. Pixel arrays did not accumulate with batch size in these tests. SQLite task listings and the initial path/hash snapshot still grow with exposure count. This is evidence against proportional image-memory growth for the measured workload, not proof of long-run leak freedom. Throughput at 10 frames scaled 1.85× with two workers and 2.84× with four; native exception and process startup costs are part of the measurement.

**VERIFIED one detector-size synthetic exposure.** A separate single-process 3856 × 2180 trial used five frames per master and a 1024 MiB budget. Dark, flat-dark and flat builds took 3.05, 2.73 and 3.32 s. Calibration took 1.15 s and QC 1.98 s, total reduction to a checksummed PARTIAL publication took 4.72 s, and existing-product verification and reuse took 0.61 s. Peak process working set including master building was 834.8 MiB. This is not a full-size throughput scaling test.

**VERIFIED code path, PARTIALLY VERIFIED I/O impact.** Each worker streams a full SHA-256 read of both science masters before reading needed FITS tile subsets. The current six planes store 34 bytes/pixel, so the two masters alone represent about 572 MB of logical checksum reads for each 8,406,080-pixel light, plus raw and product reads. The OS can cache those bytes. Neither physical disk bandwidth nor the contribution of repeated master reads to large-batch wall time was isolated. Replacing process isolation or eliminating read checks would require fresh integrity and crash evidence. Worker-count tuning must account for the per-worker memory budget and index RAM; four concurrent full-size workers were not tested.

**VERIFIED synthetic recovery.** Tests exercise process exit code 28 and retry, a simulated persisted in-flight checkpoint, changed-raw quarantine, concurrent publication of a duplicate input and rollback after a staged-write exception. Completed job reentry returned identical outcome receipts without rewriting products in these runs. Physical interruption or power-loss durability and subordinate solver cleanup remain UNVERIFIED.

Reproduce with `python benchmarks/batch_commission.py` (requires psutil) and `python benchmarks/synthetic.py --shape 2180 3856`. The [batch JSONL](batch.jsonl) and [full frame timing](full-frame.json) report the observed samples.
