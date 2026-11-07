# Leakage audit

Every finding has a check id, a status, evidence, and a remedy.

| Status | Meaning |
| --- | --- |
| `CONFIRMED` | A concrete violation, with named rows, columns, or times. |
| `WARNING` | A heuristic or an incomplete signal. Inspect it. |
| `NOT_CHECKED` | The check did not run, or the fields needed to decide it are absent. |
| `PASS` | The check ran and found no violation. |

If `available_at` was not supplied, delayed-record leakage is `NOT_CHECKED`, not `PASS`. An empty finding list is also `NOT_CHECKED`. `with_documented_coverage` adds a `NOT_CHECKED` row for every known check that has no finding, so the report shows what it did not cover.

A confirmed `fail_on` check will abort training after the report is written and exit with code 1. That behavior is specified and not implemented yet.

## v0.1 checks

`random_split`, `future_labels`, `future_in_features`, `post_event_features`, `delayed_record_leak`, `interpolation_leak`, `entity_leakage`, `scaler_leakage` (this id also covers transformer membership), `target_in_features`, `event_metadata_in_features`, `silent_negative_censoring`, `unsupported_history`, `replacement_episode_mix`, `test_used_for_choices`, `official_hidden_label_reconstruction`.

`unsupported_history` is the v0.1 check that a censored or unsupported trajectory was dropped or relabeled without a finding. The allowed dispositions are `reject` and `report`.

`high_association_with_label` and `backend_internal_split` warn by default.

Fleet alert metrics are not a v0.1 check result. In the report JSON they are not omitted and they are not zero. Each one is an object:

```json
{"value": null, "status": "NOT_COMPUTED"}
```

A metric the configuration turns off uses `"status": "DISABLED"` and the same null value. A metric with a number uses `"status": "COMPUTED"`.

## Gap policy

`none` leaves missing values missing. `ffill` may fill forward only up to `max_gap`, only from a value that was already knowable, and not across a replacement or a split. Linear interpolation is a confirmed leak and is rejected in configuration.
