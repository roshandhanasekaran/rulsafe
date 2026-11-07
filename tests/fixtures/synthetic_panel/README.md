# Synthetic panel

These fixtures are not generated yet. The later suite needs a tiny panel with no third-party data:

- a completed trajectory that can pass the audit
- a censored or unsupported history. `reject` stops the run with an error. `report` excludes it from every split, continues, and records it
- a delayed record (`available_at` after `event_time`)
- a replacement that starts a new episode
- a future value planted in a window
- a target column and an event-metadata column planted as features
- a scaler fitted on more than the training rows

Default continuous integration uses these fixtures. It does not download C-MAPSS or SCANIA Component X.
