# v0.1.0 critical review and validation

Review date: 2026-11-08. The initial implementation self-review was followed
by a separate code-review agent and a QA agent, each independently inspecting
and testing the five-PR candidate at `89863fd`. Both reproduced the grouping
issue recorded below. These agent reviews do not replace an independent
maintainer approval. Changes remain in stacked PRs; `main` and repository
visibility have not been changed.

## Defects resolved

| Finding | Effect before the change | Resolution and evidence |
| --- | --- | --- |
| Degenerate cross-version reference | The numerical guard locked RMSE near zero on a smoke panel where remaining life is a direct rearrangement of pressure. This could be mistaken for demo performance. | The guard now runs the noisy demo fleet with actual cross-version measurements and a strictly absolute tolerance. The panel stays in contract tests. FD001 is unaffected. |
| Missing installed-demo resources | A built wheel failed outside the checkout because its YAML was absent; the FD001 path could fail before showing fetch instructions. | Bundle canonical YAML resources; generate first-party synthetic tables temporarily; run a clean installed-wheel check outside the checkout in CI. Test a poisoned local examples directory as well. |
| Incomplete onboarding and scope statements | Old docs mixed working commands with stubs and did not provide an executable user-data column map. | Run every README Python snippet and YAML against renamed full input tables; compare the actual report with the documented excerpt. Explicitly state unsupported horizon tasks and date parsing. |
| Repaired episodes can cross physical-machine splits | The new episode-ID advice did not preserve physical-machine holdout. The inherited splitter also accepted an alternate `group_column` but silently split episode IDs; both agents reproduced physical machines in train and test with `entity_leakage: PASS`. | Schema and pre-fit runtime guards now reject unsupported grouping. Three regressions check validation, a stored-config bypass, and valid machine-preserving partition files. README and audit docs require caller-constructed physical-machine partitions and state the audit cannot infer parent hardware. |
| Incomplete release metadata | Version/citation still described the foundation; source links were absent and candidate distributions were not retained/tested as installed packages. | Prepare matching 0.1.0 metadata, explicit SPDX/license files, source links, clean-wheel checks, audited SBOM, and private artifact retention. No publication is configured. |

## Evidence

- Unmodified `cb1136e`: **141 passed, 91.48% branch-inclusive coverage** on
  Python **3.11.17, 3.12.15, 3.13.17**. These are the available interpreters,
  not the patch versions in the initial handoff.
- Original candidate at `89863fd`: independently repeated **142 passed,
  91.49% branch-inclusive coverage** on each interpreter.
- Candidate with the grouping correction: **145 passed, 91.52%
  branch-inclusive coverage** on each of Python **3.11.17, 3.12.15, 3.13.17**.
  The three added tests check unsupported grouping and supplied partitions.
- Official FD001: measured RMSE **16.65538791185784**, MAE
  **12.119968435305868**, NASA sum **665.7298894865181**, constant RMSE
  **41.821494536757605**. The 95% engine-bootstrap tree RMSE interval is
  **13.848876888537985–19.20071043840979** on Python 3.12.15. Cross-version
  differences are below `1e-9`; see the [full record](../benchmarks/verification-cb1136e.md).
- Physical NASA battery data: the generic API completes on all three
  interpreters, preserves the censored cell, and retains small-split and
  high-association warnings. An extra target-column plant writes `FAILED`
  with `target_in_features` confirmed. See the [source, conversion, measured
  outputs, and limitations](../benchmarks/nasa-battery-smoke.md).
- Clean wheel installs: metadata, resources, CLI help/version, synthetic
  HTML/JSON output, and missing-FD001 guidance pass on all three interpreters.
  The source archive also builds and installs separately.
- Strict metadata/rendering check: **Twine 7.0.0** passes both the wheel and
  source archive. CFF schema validation checks citation metadata separately.
- Ruff, formatting, strict mypy, pre-commit, Bandit, full-history Gitleaks,
  and dependency audits for all three hashed locks pass. Audits ignore no
  advisories. The build SBOM is generated from the Python 3.12 lock.

## Security, packaging, and licence review

Configuration uses `yaml.safe_load`. Reports escape dynamic HTML text and
embed their styles locally; an HTML-injection probe remains escaped. Dataset
fetching requires HTTPS and verifies pinned outer and inner hashes. Archive
members are selected by name rather than extracted to caller-controlled paths.
The pipeline has no telemetry, hosted execution, or model-deserialization path.
Fitting uses only the training split; validation selects iterations/model;
the final test is scored without changing either choice. Existing planted
leakage and invariance tests enforce these boundaries.

The wheel includes code, `py.typed`, two YAML configurations, distribution
metadata, Apache-2.0 LICENSE, and NOTICE. No downloaded dataset is bundled.
The sdist includes first-party fixtures but excludes local datasets/runs and
environment files. Runtime dependency ranges and all hashed dependency pins
are unchanged; no lock regeneration was needed for metadata-only edits.

CI has `contents: read`, no publish job, no publishing token, and no OIDC write
permission. The new artifact-upload action is pinned by commit. Private
workflow artifacts hold build outputs; no PyPI/TestPyPI upload or public
GitHub Release has been created. Scanner results are evidence for this
candidate and advisory snapshot, not a claim that all possible defects were found.

## Scope and known limits

- Only completed-trajectory RUL is implemented. `failure_within_horizon`,
  SCANIA, global-time splits, alert metrics, and generic CLI `init`, `profile`,
  `check`, `train`, and `report` are deferred. Use the Python API for own data.
- Inputs currently need numeric time and an explicit Assets list. Separate
  repaired/replaced histories need separate component-episode IDs, and all
  completed episodes of each physical machine must stay in one supplied partition.
  `group_holdout.group_column` must match `assets.id_column`; alternate parent
  grouping is rejected. The audit does not infer shared physical hardware
  from distinct episode IDs.
- FD001 is simulated engine data and has no ingestion-delay field, so its
  delayed-record finding stays `NOT_CHECKED`. Its scores do not establish
  performance on a physical fleet.
- The physical battery split has one completed cell per split. Its many rows
  do not provide many independent test entities. Its metrics are an execution
  smoke check, not a generalization claim or an official NASA benchmark.
- Association is a heuristic, not proof of causality. Warnings in the
  synthetic and physical examples remain visible rather than being tuned away.
- NASA catalog licences are not specified. Third-party files are not
  redistributed; their terms are separate from this code's Apache-2.0 licence.
- Input tables and downloaded archives are processed in memory. No streaming
  or arbitrary-scale performance claim is made.

## Remaining owner decisions

Review the PRs and their final CI, approve their merge, and separately decide
when to make the repository public. Publishing configuration, project-name
registration, release date/tag, and PyPI publication require the owner's later
release decision. The [release procedure](releasing.md) records those steps.
The independent code review and QA reproduced one material issue in this
candidate: unsafe grouping guidance combined with an ignored grouping setting.
The code reviewer rechecked the correction against the original counterexample,
the `model_copy` bypass, explicit physical-machine partitions, and all three
new regressions, finding no further issue. QA separately repeated the schema
and pre-fit rejection paths, machine-preserving explicit partitions, the README
quickstart, and a fresh runtime-only wheel installation. It found no remaining
reproduced blocker. Physical-machine identity still depends on the caller's
partition mapping. The corrected commit and artifacts must pass final CI and
owner review; these agent checks do not replace an independent maintainer review.
