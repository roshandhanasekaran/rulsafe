# Synthetic panel

This tiny panel is the unit smoke fixture. Every completed engine fails at cycle 2 and `pressure` is the cycle plus one, so remaining life is `3 - pressure`. Its near-zero tree error is expected and is not evidence of predictive performance. It is neither the demo nor the cross-version metric reference; those use the noisy fleet in `examples/synthetic_fleet.yaml`. The suite uses this panel for:

- a completed trajectory that can pass the audit
- a censored or unsupported history. `reject` stops the run with an error. `report` excludes it from every split, continues, and records it
- a delayed record (`available_at` after `event_time`)
- a replacement that starts a new episode
- a future value planted in a window
- a target column and an event-metadata column planted as features
- a scaler fitted on more than the training rows

Default continuous integration uses these fixtures. It does not download C-MAPSS or SCANIA Component X.
