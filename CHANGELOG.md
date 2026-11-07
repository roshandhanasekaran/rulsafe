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
- Command-line commands for the later pipeline. `validate` and `datasets list` work. `demo cmapss` does not download FD001.
- Ruff, mypy, pytest, pre-commit, bandit, gitleaks, and pip-audit wiring.

### Added

- `rulsafe demo synthetic` runs the CSV group-holdout slice. Causal features ignore later rows. The censored asset stays in `report.json`. The constant and histogram gradient boosting baselines use training rows only. Early stopping uses validation. Root-mean-square error, mean absolute error, and the NASA score are reported. The NASA score is not a gate.

### Changed

- `global_time` and alerts are rejected. The error says both are deferred to v0.2.
- Bandit B105 is not skipped globally. The leakage status `PASS` carries a targeted `# nosec B105`.
- Dependency audit uses one hashed lock per Python version, `requirements/dev-3.11.lock`, `requirements/dev-3.12.lock`, and `requirements/dev-3.13.lock`. CI installs that file with `--require-hashes` and ignores no advisories.
- Python 3.10 is not supported. `requires-python` is `>=3.11`. The 3.10 lock and the filelock ignore list are removed.
- The build backend is pinned to `hatchling==1.33.0`.
- Gitleaks in CI scans the full git history.
- `censored_policy: reject` writes a partial report with status `FAILED`, lists the contract violations, omits metrics, and then raises. `censored_policy: report` excludes the history from every split, continues, and names it in the report.
- `min_assets_per_split` defaults to 3. A smaller split is a warning in `risks`. The synthetic demo's one-asset validation and test splits warn, and their scores stay `COMPUTED`. An empty split is `NOT_COMPUTED` with that reason in `risks`.
- Ruff's `target-version` is `py311`.
- `scikit-learn` is a runtime dependency. The hashed locks for Python 3.11, 3.12, and 3.13 include it.

### Not in this release

- Official C-MAPSS partition scoring, HTML reports, and dataset downloads. `rulsafe demo cmapss` does not download FD001.
