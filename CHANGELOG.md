# Changelog

## 0.0.1 — 2026-11-07

Foundation release. The package installs, the v0.1 schema validates, and the command-line skeleton answers `--help` and `--version`. The training pipeline is not implemented.

### Added

- Completed-trajectory configuration schema: train / validation / test protocols, causal gap rules, and train-only preprocessing fields.
- Baselines limited to a training constant and one histogram gradient boosting model. Persistence, age, and logistic regression are rejected.
- `censored_policy` of `reject` or `report`. Silent drop policies are configuration errors. SCANIA and `failure_within_horizon` are rejected until v0.2.
- Dataset cards for C-MAPSS FD001 (v0.1 demo; NASA catalogue licence not specified; Zenodo CC BY 4.0 kept separate) and SCANIA Component X (v0.2, CC BY 4.0, 105 signal columns).
- Audit helpers that record a missing check as `NOT_CHECKED` rather than a pass.
- Report metrics serialise as `{"value": null, "status": "DISABLED"}` or `{"value": null, "status": "NOT_COMPUTED"}` when they have no number. A computed metric uses the same keys with a finite value and `"COMPUTED"`.
- Command-line commands for the later pipeline. `validate` and `datasets list` work. `demo cmapss` is reserved and not implemented.
- Ruff, mypy, pytest, pre-commit, bandit, gitleaks, and pip-audit wiring.

### Added

- `rulsafe demo synthetic` runs the CSV group-holdout slice. Causal features ignore later rows. The censored asset stays in `report.json`. The constant baseline uses training targets only. The tree metric is `NOT_COMPUTED`.

### Changed

- `global_time` and alerts are rejected. The error says both are deferred to v0.2.
- Bandit B105 is not skipped globally. The leakage status `PASS` carries a targeted `# nosec B105`.
- Dependency audit uses `requirements/dev.lock`, resolved from the project extras in a clean virtualenv.
- Gitleaks in CI scans the full git history.

### Not in this release

- Windowing, labeling, splits, model fitting, C-MAPSS scoring, HTML or JSON reports, and dataset downloads.
