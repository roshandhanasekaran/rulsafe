# v0.1.0 critical review and validation

Review date: 2026-11-08. PRs 7–13 are merged into the private, unpublished
`main` branch. The integration point `6907bb1` passed the complete local and
GitHub Actions matrices. A separate code-review agent and QA agent inspected
the follow-up PRs, constructed integration trees, and repeated adversarial,
cross-version, and installed-package checks. These reviews do not replace
maintainer approval.

The reviewed follow-up heads are:

| PR | Head | Scope |
| --- | --- | --- |
| [7](https://github.com/roshandhanasekaran/rulsafe/pull/7) | `eb23efb` | Runtime table contract |
| [8](https://github.com/roshandhanasekaran/rulsafe/pull/8) | `1198efa` | NASA milling physical-data smoke check |
| [9](https://github.com/roshandhanasekaran/rulsafe/pull/9) | `0705058` | Reject configuration without runtime behavior |
| [10](https://github.com/roshandhanasekaran/rulsafe/pull/10) | `c7cf11f` | Report metadata and ordering |
| [11](https://github.com/roshandhanasekaran/rulsafe/pull/11) | `2970d31` | Hermetic mypy pre-commit hook |
| [12](https://github.com/roshandhanasekaran/rulsafe/pull/12) | `e4a653c` | Exported JSON and terminal report writers |
| [13](https://github.com/roshandhanasekaran/rulsafe/pull/13) | `6e38091` | Documentation consistency and final review record |

## Defects resolved

| Finding | Effect before the change | Resolution and evidence |
| --- | --- | --- |
| Degenerate cross-version reference | The numerical guard locked RMSE near zero on a smoke panel where remaining life is a direct rearrangement of pressure. This could be mistaken for demo performance. | The guard runs the noisy demo fleet with measured cross-version output and a strictly absolute tolerance. The panel stays in causal and contract tests. FD001 is unaffected. |
| Missing installed-demo resources | A built wheel failed outside the checkout because its YAML was absent; the FD001 path could fail before showing fetch instructions. | Bundle the canonical YAML resources, generate first-party synthetic tables temporarily, and run installed-wheel checks outside the checkout. |
| Repaired episodes can cross physical-machine splits | An alternate `group_column` was accepted while the runtime still split episode IDs, allowing episodes from one physical machine into different splits. | Schema and pre-fit guards reject unsupported grouping. Supplied partitions remain the supported way to keep all episodes of a physical machine together. The audit states that it cannot infer a parent machine from episode IDs. |
| Physical tables were trusted too far into the run | Missing configured columns, blank or duplicate IDs, nonnumeric/nonfinite values, impossible availability times, and unsupported terminal histories could reach later pipeline stages. | Validate physical schemas and cells before preprocessing or fitting. Report or reject unsupported histories explicitly. Reversed valid row order produces the same result. |
| CSV and Parquet structure could hide bad values | Duplicate headers could replace an earlier ID or sensor value; short/long CSV rows, blank headers, invalid UTF-8, and duplicate Parquet names were not uniformly rejected. | Parse strict CSV row widths and headers, inspect Parquet schema names before reading, and wrap invalid encoding as a configuration error. Both reviewers repeated the original probes before model fitting. |
| Accepted configuration had no runtime effect | Several schema fields suggested support for dates, resampling, observation bounds, horizon tasks, plots, Markdown, and replacement behavior that v0.1 did not execute. Model and leakage-selection fields could also omit behavior the pipeline always relied on. | Reject the unimplemented settings, require the constant reference model, and require every leakage check to appear in exactly one of `fail_on` or `warn_on`. A confirmed warning-only finding remains visible and does not abort the run. |
| Reports dropped declared metadata or ordering | Configured title, project notes, label unit, timestamp type, and split order did not consistently reach JSON/HTML. Nested FD001 blocks initially still used their fixed order. | Preserve the fields and apply the requested split order to top-level and nested blocks. The code-review counterexample with test before validation now passes without changing the metrics. |
| Exported report functions were stubs | `rulsafe.report.write_json_report` and `render_terminal_summary` were public imports but raised `NotImplementedError`. | Implement one strict JSON writer used by the API and pipeline, plus a printable terminal summary. Non-finite JSON is rejected without overwriting an existing file; terminal control characters are removed. |
| Isolated mypy hook depended on the developer environment | A cold pre-commit environment could not resolve runtime library types. | Declare scikit-learn and PyArrow in the hook environment. QA repeated the cold isolated hook; the code reviewer ran strict mypy with a fresh cache. |
| Release metadata and evidence were incomplete | Version/citation still described the foundation; source links and installed-distribution checks were incomplete. | Prepare matching 0.1.0 metadata, Apache-2.0 files, source links, clean wheel/sdist checks, an audited SBOM, and private artifact retention. No publication is configured. |

## Measured evidence

- Unmodified `cb1136e`: **141 passed, 91.48% branch-inclusive coverage** on
  Python **3.11.17, 3.12.15, and 3.13.17**. These are the available
  interpreters, rather than the patch versions in the initial handoff.
- The earlier candidate with the physical-grouping correction: **145 passed,
  91.52% branch-inclusive coverage** on all three interpreters.
- QA's exact six-PR integration tree object
  `754a2a8f57dacb105a7c99c5f321075848f0ec3b`: **185 passed, 91.75%
  branch-inclusive coverage** on each of Python 3.11.17, 3.12.15, and 3.13.17.
  This is a recorded Git tree, not a release commit.
- The code reviewer loaded that exact canonical tree and independently measured
  **185 passed, 91.75% branch-inclusive coverage** on Python 3.12.15. Ruff and
  strict mypy also pass on that tree.
- Every individual PR above completed its nine CI jobs: lint/types, security,
  the three Python test jobs, the three hashed-lock audits, and the wheel build.
  After integration, private `main` at
  [`6907bb1`](https://github.com/roshandhanasekaran/rulsafe/commit/6907bb1e520b6476ebcc5c418ff5dd40f6b6b7df)
  produced **185 passed, 91.75% branch-inclusive coverage** on each of Python
  3.11.17, 3.12.15, and 3.13.17. Its
  [nine-job workflow](https://github.com/roshandhanasekaran/rulsafe/actions/runs/42501036934)
  also passed.
- Official FD001 tree RMSE is **16.65538791185784**, MAE is
  **12.119968435305868**, NASA sum is **665.7298894865181**, and constant RMSE
  is **41.821494536757605**. The Python 3.12.15 95% engine-bootstrap tree RMSE
  interval is **13.848876888537985–19.20071043840979**. Cross-version
  differences are below `1e-9`; see the
  [full record](../benchmarks/verification-cb1136e.md).
- The [physical NASA battery smoke check](../benchmarks/nasa-battery-smoke.md)
  completes on all three interpreters with tree test RMSE
  **12.43840298117819** and constant test RMSE **31.047007370544858**. It
  preserves the censored cell and its small-split and association warnings. A
  planted target column produces a `FAILED` report.
- The NASA milling smoke check in PR 8 uses physical current, vibration, and
  acoustic-emission traces. Fifteen completed cases and one censored case are
  produced by the documented first-observed 0.30 mm wear scenario. On all
  three interpreters the selected constant test RMSE is
  **2.7271481351130276**, MAE is **2.525096525096525**, and NASA sum is
  **0.9277325849191542**. The split has only two validation and two test cases;
  the record explicitly makes no accuracy or generalization claim.
- Malformed input probes cover duplicate Assets/Readings/Events headers,
  duplicate Parquet names, blank headers, missing and extra CSV cells, invalid
  UTF-8 and quoting, non-finite values, blank/repeated IDs, and events for
  unregistered assets. A valid quoted ID containing Unicode, a comma, and a
  newline survives unchanged.
- A fresh runtime-only wheel on Python 3.11 and source archive on Python 3.13
  pass the README/grouping acceptance path, completed/censor-rejected/leakage-
  failed reports, metadata and ordering checks, HTML escaping, strict JSON,
  and terminal-summary probes. Earlier checks also installed the wheel on all
  three interpreters and passed Twine 7.0.0 for wheel and source archive.
- Fresh wheel and source artifacts built from integrated commit `6907bb1`
  passed strict Twine checks, an isolated installed-package check, `pip check`,
  and a dependency audit. Installing its source archive reproduced the tested
  wheel byte for byte. The artifacts must be rebuilt after this documentation
  update because it changes source-archive content.
- All **50** wheel code/resource files and all **118** tracked sdist files match
  integrated commit `6907bb1` byte for byte. `PKG-INFO` is the sdist's only
  generated extra; neither distribution contains downloaded dataset files.
- Ruff, formatting, strict mypy, pre-commit, Bandit, full-history Gitleaks, and
  dependency audits for all three hashed locks pass. No advisory is ignored.

## Security, packaging, and licence review

Configuration uses `yaml.safe_load`. Reports escape dynamic HTML, keep styles
local, reject non-finite JSON, and strip terminal control characters. Strict
table parsing stops ambiguous schemas and malformed records before fitting.
The pipeline has no telemetry, hosted execution, or model-deserialization
path. Training-only preprocessing, validation-only selection, final-test
scoring, planted leaks, future-row invariance, and row-order invariance all
have executable checks.

C-MAPSS fetching requires HTTPS and verifies pinned outer and inner hashes.
Archive members are selected by name rather than extracted into caller paths.
The milling script verifies its outer archive, nested archive, and MAT-file
hashes and reads them without extraction. Third-party data remain outside the
repository and distributions.

The wheel contains code, `py.typed`, two demo YAML files, package metadata,
LICENSE, and NOTICE. The sdist contains first-party fixtures and excludes
downloaded data, local runs, secrets, and environments. CI has `contents: read`,
no publishing job, no PyPI token, and no OIDC write permission. Private build
artifacts contain the distributions, checksums, and the Python 3.12 build-lock
CycloneDX SBOM.

## Scope and known limits

- v0.1 implements completed-trajectory RUL. `failure_within_horizon`, native
  calendar-date parsing, SCANIA, global-time splits, alerts, plots, and generic
  CLI `init`, `profile`, `check`, `train`, and `report` execution are deferred.
  The configuration rejects unsupported choices.
- The public run path uses `run_pipeline`. Internal standalone mapping,
  generic leakage-registry, and plot-rendering entry points remain reserved
  placeholders and are not called by the pipeline.
- Inputs need numeric time and an explicit Assets list. Repaired/replaced
  histories need separate episode IDs, with all episodes from one physical
  machine kept in a caller-supplied partition. The audit cannot infer that
  parent relationship.
- FD001 is simulated and has no ingestion-delay field, so delayed-record
  leakage remains `NOT_CHECKED`. Its score does not establish performance on
  physical equipment.
- The physical battery split has one completed cell per split. The physical
  milling split has two cases each in validation and test, all collected on one
  machining centre. Both are execution checks rather than official benchmarks
  or evidence of model generalization.
- Association is a heuristic rather than proof of causality. Warnings remain
  visible instead of being tuned away.
- NASA catalog/archive licences are not specified. The project does not
  redistribute those files; their terms are separate from the code's
  Apache-2.0 licence.
- Tables and downloaded archives are processed in memory. No streaming or
  arbitrary-scale performance claim is made.

## Work remaining before release

The code-review and QA agents report no reproduced runtime blocker in the
six-PR code integration, and PRs 7–13 are merged. The remaining engineering
gate is to review and merge this documentation-only status update, repeat CI
on the resulting `main`, and rebuild and inspect artifacts from that exact
commit.

Repository visibility, the release date/tag, GitHub Release, PyPI project-name
registration, trusted-publishing configuration, and upload remain separate
owner decisions. None has been changed or performed. The
[release procedure](releasing.md) records those gates.
