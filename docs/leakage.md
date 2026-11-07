# Leakage audit

Every finding has a check id, a status, evidence, and a remedy.

| Status | Meaning |
| --- | --- |
| `CONFIRMED` | A concrete violation, with named rows, columns, or times. |
| `WARNING` | A heuristic or an incomplete signal. Inspect it. |
| `NOT_CHECKED` | The check did not run, or the fields needed to decide it are absent. |
| `PASS` | The check ran and found no violation. |

If `available_at` was not supplied, delayed-record leakage is `NOT_CHECKED`, not `PASS`. An empty finding list is also `NOT_CHECKED`. `with_documented_coverage` adds a `NOT_CHECKED` row for every known check that has no finding, so the report shows what it did not cover.

A confirmed `fail_on` check aborts the run after `report.json` and `report.html` are written. The report status is `FAILED`, and the command exits with code 1.

## v0.1 checks

`random_split`, `future_labels`, `future_in_features`, `post_event_features`, `delayed_record_leak`, `interpolation_leak`, `entity_leakage`, `scaler_leakage` (this id also covers transformer membership), `target_in_features`, `event_metadata_in_features`, `silent_negative_censoring`, `unsupported_history`, `replacement_episode_mix`, `test_used_for_choices`, `official_hidden_label_reconstruction`.

`unsupported_history` is the v0.1 check that a censored or unsupported trajectory was dropped or relabeled without a finding. `censored_policy: reject` stops the run with an error. `report` excludes the history from every split, continues, and names it in the report.

`high_association_with_label` and `backend_internal_split` warn by default.

`global_time` and alerts are not v0.1 features. A configuration that asks for either is rejected with an error that says they are deferred to v0.2.

When a metric has no number, the report JSON does not omit it and does not store zero:

```json
{"value": null, "status": "NOT_COMPUTED"}
```

A metric the configuration turns off uses `"status": "DISABLED"` and the same null value. A metric with a number uses `"status": "COMPUTED"`. An empty split uses `"status": "NOT_COMPUTED"` and the report `risks` state that reason. Root-mean-square error and mean absolute error are the primary scores. The NASA asymmetric score is one Saxena 2008 term per engine, summed across engines, and is not a `fail_on` check. Test RMSE and MAE include a percentile bootstrap over engines. Histogram gradient boosting is fit on the training split only. Early stopping and model selection use the validation split and do not draw a random internal split of the training rows. The report labels those validation metrics `used for early stopping/selection`. The headline evaluation is the test split. `censored_policy: reject` writes each offending asset id with its signal, event, and prediction row counts before it stops.

## Gap policy

`none` leaves missing values missing. `ffill` may fill forward only up to `max_gap`, only from a value that was already knowable, and not across a replacement or a split. Linear interpolation is a confirmed leak and is rejected in configuration.
