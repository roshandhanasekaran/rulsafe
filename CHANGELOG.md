# Changelog

## 0.1.0 — Unreleased

Prepared for review; not published to PyPI. The repository remains private
pending owner approval.

### Added

- v0.1.0 candidate package metadata, source links, explicit Apache-2.0 licence
  files, and matching citation version. No publication date is assigned yet.
- CI installs the built wheel in a clean environment, runs its demos outside
  the checkout, and retains candidate distributions, checksums, and an audited
  build-environment CycloneDX SBOM as private workflow artifacts. There is no
  publishing job or publishing credential.
- Opt-in integration check on physical NASA battery sensor measurements with
  documented capacity-defined end-of-life labels and censored-cell reporting.
  Its single-cell held-out split is a smoke check, not a performance benchmark.
- Equipment-agnostic introduction and an executable Readings / Events / Assets
  column-map quickstart. v0.1 supports completed-trajectory RUL; failure-within-
  horizon tasks and censored-fleet classification remain deferred.
- Independent verification of `cb1136e` on Python 3.11.17, 3.12.15, and
  3.13.17: 141 tests pass with 91.48% branch-inclusive coverage on each version.
- Recorded official FD001 results: tree RMSE 16.6554 (95% engine-bootstrap
  interval 13.85–19.20), MAE 12.12, and NASA sum 665.73. Constant RMSE 41.82.
  See [verification details](benchmarks/verification-cb1136e.md).

### Fixed

- Validate configured physical-table columns and cells before fitting. Missing
  sensor columns, blank or repeated Assets IDs, malformed or non-finite numeric
  values, and impossible `available_at` times now raise a configuration error.
  Terminal histories with no pre-event reading are reported as unsupported,
  and events for unregistered assets can no longer disappear from the audit.
- Reject a `group_holdout.group_column` that differs from `assets.id_column`
  instead of silently splitting episode IDs. Validation and the runtime
  guard both stop unsupported grouping before fitting. Repaired histories
  must use supplied partitions that keep every episode of a physical machine
  together; documentation now states the audit cannot infer parent hardware
  from episode IDs. Found independently by the code-review and QA agents.
- Installed demos resolve bundled configurations outside a source checkout.
  Synthetic inputs are generated locally from the existing deterministic fleet;
  no dataset files are added to the wheel. Missing FD001 tables produce the
  documented fetch instructions instead of a missing-configuration error.
- Cross-version metrics now reference the noisy synthetic demo fleet, whose
  measured tree test RMSE is 1.9655398693652688. The 0.00739044155925539 smoke
  panel result comes from `remaining_life = 3 - pressure` and is not a useful
  accuracy benchmark. The panel remains for causal and contract tests.
- The documented absolute test tolerance is enforced with `rel=0`.

### Scope and limits

- Completed-trajectory RUL, CSV/Parquet inputs, causal last/mean/slope features,
  training-only clipping/scaling, validation-only model selection, and local
  HTML/JSON reports are implemented.
- Confirmed configured leakage failures write `FAILED` reports. Missing audit
  evidence stays `NOT_CHECKED`; missing metrics stay null. FD001 has no
  `available_at`, so delayed-record leakage remains unchecked.
- `failure_within_horizon`, SCANIA, global-time splits, alerts, native date
  parsing, and the generic `check`/`train` CLI commands are not implemented.


## 0.0.1 — 2026-11-07

Foundation release. The package installs, the v0.1 schema validates, and the completed-trajectory pipeline writes `report.json` and `report.html`.

### Added

- Completed-trajectory configuration schema: train / validation / test protocols, causal gap rules, and train-only preprocessing fields.
- Baselines limited to a training constant and one histogram gradient boosting model. Persistence, age, and logistic regression are rejected.
- `censored_policy` of `reject` or `report`. Silent drop policies are configuration errors. SCANIA and `failure_within_horizon` are rejected until v0.2.
- Dataset cards for C-MAPSS FD001 (v0.1 demo; NASA catalogue licence not specified; Zenodo CC BY 4.0 kept separate) and SCANIA Component X (v0.2, CC BY 4.0, 105 signal columns).
- Audit helpers that record a missing check as `NOT_CHECKED` rather than a pass.
- Report metrics serialise as `{"value": null, "status": "DISABLED"}` or `{"value": null, "status": "NOT_COMPUTED"}` when they have no number. A computed metric uses the same keys with a finite value and `"COMPUTED"`.
- Command-line commands for the later pipeline. `validate` and `datasets list` work. `demo cmapss` reads converted tables and does not download them.
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
- `scikit-learn` and `pyarrow` are runtime dependencies. The hashed locks for Python 3.11, 3.12, and 3.13 include them. `pyarrow` is pinned at 23.0.1 or newer so the lock is clear of PYSEC-2026-113.
- `rulsafe data fetch cmapss` downloads the NASA Prognostics outer zip, checks the pinned outer and inner SHA-256 values, and writes git-ignored FD001 Parquet tables. `--from-file` accepts a local outer or inner zip. Completed training engines are split in unit-number order. NASA test engines are censored and excluded. `RUL_FD001.txt` is not a label. See [docs/cmapss-fd001.md](docs/cmapss-fd001.md).
- `rulsafe demo synthetic` uses a deterministic noisy fleet with varied lifetimes and four drifting sensors. Every split has at least three assets. The tiny panel remains the unit smoke fixture.
- Validation metrics are labeled `used for early stopping/selection`. The headline evaluation is the test split of the model selected on validation root-mean-square error.
- A rejected history's partial report names the offending asset and its signal, event, and prediction row counts.
- The FD001 headline score is the last observation of each official test engine against `RUL_FD001.txt`. Held-out training engines supply the protocol validation. Per-row scores on those engines stay as a labelled secondary view. `target.rul_cap` defaults to none and is 125 in the C-MAPSS example. The NASA score sums one Saxena 2008 term per engine.
- Clip percentiles and the standard scaler are fit on the training split. `windows.lookback` adds a causal mean and slope beside the last value. Test RMSE and MAE include a percentile bootstrap over engines. `report.html` is written beside `report.json`. A confirmed `fail_on` check writes that report and then stops.
- Near-constant columns are centered and not divided by float dust, so the same FD001 run agrees on Python 3.11, 3.12, and 3.13. Target columns match normalized names such as `remaining_life`, and a feature that copies the target is a leak. `high_association_with_label` is the training-row Pearson check.

### Not in this release

- FD002–FD004 are not converted. The raw C-MAPSS archive is not committed.
