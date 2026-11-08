# Independent verification of cb1136e

Measured on 2026-11-08 from unmodified commit
`cb1136e174543760d94205107cfadf87ea833295` on Linux x86_64.
Dependencies were installed from each interpreter's hashed lock with
`--require-hashes --only-binary :all:`. `OMP_NUM_THREADS=1` and
`OPENBLAS_NUM_THREADS=1` were set for the runs.

| Python | Tests | Branch-inclusive coverage | scikit-learn | NumPy | SciPy | PyArrow |
| --- | ---: | ---: | --- | --- | --- | --- |
| 3.11.17 | 141 passed | 91.48% | 1.9.1 | 2.4.6 | 1.17.1 | 23.0.1 |
| 3.12.15 | 141 passed | 91.48% | 1.9.1 | 2.5.4 | 1.18.1 | 23.0.1 |
| 3.13.17 | 141 passed | 91.48% | 1.9.1 | 2.5.4 | 1.18.1 | 23.0.1 |

These are fresh runs on the versions available to this environment, not
reruns on the originally reported 3.11.18, 3.12.3, and 3.13.18.
The default suite includes planted end-to-end failures and leakage invariance
checks. No tests were skipped.

## FD001

The fetch command verified the pinned NASA outer and inner archive hashes.
The example was used unchanged: seed 7, lookback 16 (last value, causal mean,
and slope), RUL cap 125, training-only percentile clipping and standard scaling.
The first 70 completed engines fit the model; the next 15 supply validation
and early stopping; the last 15 are the secondary per-row test. The headline
scores use one last observation for each of the 100 official test engines
against `RUL_FD001.txt`.

| Python | Tree test RMSE | Tree test MAE | Tree NASA score | Constant test RMSE |
| --- | ---: | ---: | ---: | ---: |
| 3.11.17 | 16.655387911857837 | 12.119968435305868 | 665.7298894865181 | 41.821494536757605 |
| 3.12.15 | 16.65538791185784 | 12.119968435305868 | 665.7298894865181 | 41.821494536757605 |
| 3.13.17 | 16.65538791185784 | 12.119968435305868 | 665.7298894865181 | 41.821494536757605 |

The headline tree RMSE, MAE, and NASA score agree within an absolute tolerance
of `1e-9`. The NASA score is a **sum of one asymmetric term per engine**,
not a mean and not a sum over every reading. The tree keeps 40 iterations.
The engine bootstrap gives a 95% tree RMSE interval of
[13.848876888537985, 19.20071043840979] on Python 3.12.15.

`high_association_with_label` is `PASS`: the strongest training correlation
is 0.808989 for `sensor_17_mean`, below the configured 0.85 threshold.
`delayed_record_leak` is `NOT_CHECKED` because `available_at` is absent.

## The 0.0074 question

The smoke panel really is degenerate: completed engines fail at cycle 2,
`pressure = cycle + 1`, and `remaining life = 3 - pressure`. Its measured
RMSE and MAE are both 0.00739044155925539 on all three interpreters.
It remains useful for contract and causal-window tests, but its metric should
not serve as the demo's numerical reference.

The CLI already uses the separate noisy fleet, so the degenerate demo has
not returned. Its measured test metrics on all three interpreters are:

| Model | RMSE | MAE | NASA score |
| --- | ---: | ---: | ---: |
| Histogram gradient boosting | 1.9655398693652688 | 1.2852426319239971 | 0.15571061547349063 |
| Constant | 5.277395737924274 | 4.36231884057971 | 3.185969762842635 |

The tree keeps 39 iterations. Six training features reach the configured
0.85 association threshold, so the demo correctly reports `WARNING`.
Synthetic scores are a smoke check, not equipment-performance evidence.
The cross-version test now measures this fleet, with a strictly absolute
`1e-6` tolerance (`rel=0`). The tiny panel stays in the contract tests.

## Reproduce

From a checkout of the stated commit, repeat with each supported interpreter
and the matching lock:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes --only-binary=:all: -r requirements/dev-3.12.lock
python -m pip install --no-deps --no-build-isolation -e .
bash scripts/install-gitleaks.sh
export PATH="$HOME/.local/bin:$PATH"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
pytest
rulsafe data fetch cmapss
rulsafe demo cmapss --output rulsafe-runs/verify-fd001
rulsafe demo synthetic --output rulsafe-runs/verify-fleet
```

Read `metrics.test`, `confidence_intervals.headline_test`, and `leakage` in
the resulting JSON reports. Raw NASA data are git-ignored and are not part
of this verification note.
