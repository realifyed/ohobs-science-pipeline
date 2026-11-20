# OSP a4 uncertainty validation

**SYNTHETICALLY VALIDATED.** Independent trial draws use a science light with
Poisson object and dark electrons, zero-mean Gaussian read noise, and an
independent 32-frame dark master with its own Poisson and read fluctuations.
Each row uses 180,000 realizations. The analytic variance in electrons² is
`signal + 3 + 16 + (3 + 16)/32`. The 3-electron dark and 4-electron rms read
noise settings define this simulated detector. The model adds the
single-exposure temporal noise and the independent master variance once each.

| Signal in electrons | Empirical variance / truth | Mean OSP variance / truth | Within 1 ERR | Within 1.96 ERR |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 1.0093 | 1.0906 | 70.92% | 96.71% |
| 1 | 1.0016 | 1.0651 | 70.32% | 96.46% |
| 5 | 0.9976 | 1.0163 | 68.33% | 95.28% |
| 25 | 0.9949 | 1.0002 | 68.30% | 94.47% |
| 100 | 0.9957 | 0.9999 | 68.34% | 94.81% |

The photon term uses `max(raw - matched dark, 0)` as a proxy for the
nonnegative expectation. At zero signal it averages positive because of
read noise and fluctuations in the master. This inflated mean predicted
variance by 9.1% in this scenario. The same realization sets the residual
and its estimated variance, so the normalized residual is asymmetric.
About 50.05% of zero-signal science values remain negative. The numerical
change this sprint is the validation and characterization of the limitation.
The distribution and meaning of the existing ERR plane stay compatible.
For low-count inference, model the Poisson rate and read noise explicitly
or estimate the expected signal independently. Precision requires a
measured camera response and a validation set.

For shared masters, 240,000 paired realizations at two distinct signals
gave cross-exposure covariance **2.0271 e²**, versus a first-order expectation
of **2.14 e²** and a Monte Carlo standard error of **0.1551 e²**. A shared
median flat denominator induced cross-pixel covariance **2.34485 × 10⁻⁵**
in normalized flat units, versus **2.34375 × 10⁻⁵** expected when the median
index is stable. ERR encodes the conditional marginal variance. Quantifying
aperture, coadd, or repeat-observation uncertainty requires the common
calibration terms and any measured spatial covariance.

Absolute variance comparisons use the independent generative model. The
test allows a 2% variance-ratio error for 180,000 realizations, about six
normal-approximation standard errors, with room for mild Poisson kurtosis.
It compares covariance to five empirical Monte Carlo standard errors.
Existing calibration regressions cover invalid response, non-finite pixels,
missing gain, raw saturation flags, and negative science values. All real
noise parameters and real aperture coverage remain **BLOCKED** until the
acquisition checklist is executed.

Run `python benchmarks/uncertainty_commission.py` to regenerate the
machine-readable numerical evidence. See
[HST low-count uncertainties](https://spacetelescope.github.io/hst_notebooks/notebooks/STIS/low_count_uncertainties/Low_Count_Uncertainties.html)
and [EMVA 1288 Linear](https://www.emva.org/wp-content/uploads/EMVA1288Linear_4.0Release.pdf).
