# RULSafe

RULSafe is a free, Apache-2.0 Python pre-training check for failure-prediction
data. It helps data scientists and reliability engineers find leakage and
other reasons not to trust a result before investing in a model.

Bring sensor **Readings**, failure/repair **Events**, and a configuration that
maps your columns and states the prediction question. The design is equipment
agnostic: machine IDs can identify engines, pumps, batteries, or components.
Fleet data are an initial focus, rather than a requirement.

**v0.1 implements remaining useful life (RUL) on completed trajectories.**
It builds causal features, audits the split and preprocessing, fits two small
sanity-check baselines, and writes local HTML and JSON reports. Questions such
as “failure within 7 days,” censored-fleet classification, alert metrics, and
global-time splits are deferred. The configuration rejects them explicitly.
A pass covers the checks that ran; it is not a guarantee that all leakage was
found. This is research software, not a safety-certified prognostic.

## Install

Use Python 3.11, 3.12, or 3.13. The release is being prepared and has not been
published to PyPI. While the repository is private, cloning requires access:

```bash
git clone https://github.com/roshandhanasekaran/rulsafe.git
cd rulsafe
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install .
```

No optional dependency is needed for HTML reports. Development installation
uses the hashed lock for your interpreter; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Quickstart

From the checkout root, run the local noisy-fleet example:

```bash
rulsafe demo synthetic --output rulsafe-runs/synthetic
```

Open `rulsafe-runs/synthetic/report.html` or read `report.json`. This example
completes with a leakage **WARNING**: six training features reach the configured
absolute-correlation threshold of 0.85. The warning is intentional and needs
inspection. The censored unit is named and excluded from all fitting and scoring
splits. Synthetic scores demonstrate the pipeline, not real equipment accuracy.

### Your Readings, Events, and column map

CSV and Parquet are supported. The configuration calls Readings `signals`.
Use numeric cycles or elapsed steps in a common time unit. Native calendar-date
parsing is not implemented in this pipeline; convert dates before running it.
Supply `available_at` when possible: this is when a record could first have
been known, which may be later than when the measurement happened.

Readings (`readings.csv`), showing two rows from the bundled noisy fleet with
renamed ID and time columns:

```csv
machine_id,timestamp,available_at,temperature,pressure,vibration,flow
unit-01,0,0,40.6000,11.5500,0.2500,90.1500
unit-01,1,1,44.0808,12.8009,0.8642,87.2462
```

Events (`events.csv`), showing the corresponding terminal event:

```csv
machine_id,timestamp,available_at,what_happened,failure_notes
unit-01,13,13,failure,wear
```

These are excerpts, not a sufficient training dataset. Supply the full histories
of multiple independent machines for train, validation, and test. v0.1 requires
one completed component history per ID. Use separate episode IDs for repaired
or replaced histories, and keep **all completed episodes of a physical machine
in the same split** using caller-created partition files as described below. The
ratio-split quickstart assumes one ID per independent physical machine.
Keep failure notes and repair outcomes out of the sensor features. Histories
without an observed terminal event must be rejected or reported as excluded,
never silently treated as healthy.

v0.1 also requires an **Assets** file listing all machine IDs, including those
without a completed history. You can make `assets.csv` from your Readings:

```python
import csv

with open("readings.csv", newline="", encoding="utf-8") as source:
    identifiers = sorted({row["machine_id"] for row in csv.DictReader(source)})
with open("assets.csv", "w", newline="", encoding="utf-8") as destination:
    writer = csv.writer(destination)
    writer.writerow(["machine_id"])
    writer.writerows((identifier,) for identifier in identifiers)
```

Save this column map and prediction question as `run.yaml`. Paths resolve
from the working directory where you run Python:

```yaml
project: {name: my-equipment-check, seed: 7}
connector:
  type: files
  assets: assets.csv
  signals: readings.csv
  events: events.csv
assets: {id_column: machine_id}
signals:
  id_column: machine_id
  event_time_column: timestamp
  available_at_column: available_at
  timestamp_type: integer_step
  feature_columns: [temperature, pressure, vibration, flow]
events:
  id_column: machine_id
  event_time_column: timestamp
  available_at_column: available_at
  type_column: what_happened
  terminal_types: [failure]
  competing_types: [censored_end]
  forbidden_as_features: [failure_notes]
contract: {replacement_starts_new_episode: true, replacement_types: []}
labeling:
  task: completed_trajectory_rul
  unit: steps
  censored_policy: report
windows: {lookback: 16, stride: 1, discard_straddle_split: true}
split:
  protocol: group_holdout
  group_holdout:
    group_column: machine_id
    train_ratio: 0.70
    validation_ratio: 0.15
    test_ratio: 0.15
preprocessing: {clip_percentiles: [1, 99], scaler: standard}
leakage:
  fail_on:
    - random_split
    - future_labels
    - future_in_features
    - post_event_features
    - delayed_record_leak
    - interpolation_leak
    - entity_leakage
    - scaler_leakage
    - target_in_features
    - event_metadata_in_features
    - silent_negative_censoring
    - unsupported_history
    - replacement_episode_mix
    - test_used_for_choices
    - official_hidden_label_reconstruction
  warn_on: [high_association_with_label, backend_internal_split]
  association_warn_threshold: 0.85
models: {include: [constant, hist_gradient_boosting]}
evaluation: {threshold_split: validation}
report:
  formats: [html, json]
  title: Equipment data pre-check
  output_dir: rulsafe-runs/my-equipment
```

Validate the configuration, then execute it through the Python API:

```bash
rulsafe validate --config run.yaml
```

```python
from rulsafe import load_config, run_pipeline

result = run_pipeline(load_config("run.yaml"))
print(result.report_paths.html_path)
print(result.leakage.worst_status.value)
```

For repeated episodes from the same physical machine, replace the `split`
block with explicit partition files:

```yaml
split:
  protocol: official_partitions
  official_partitions:
    train_ids: train_ids.txt
    validation_ids: validation_ids.txt
    test_ids: test_ids.txt
```

Each file contains one completed episode ID per line. Build those lists from
the original physical-machine mapping so every completed episode of a machine
goes to the same file. Leave censored and unsupported histories in the input
tables, outside these partition lists; the report still names their exclusion.
Despite the configuration name, these can be your own fixed partitions.
In v0.1, `group_holdout.group_column` must equal `assets.id_column`; choosing
another column is rejected because the splitter cannot group by it. The audit
checks the supplied IDs and cannot infer shared physical hardware from episode
names, so it does not verify that your parent-machine grouping is correct.

`validate` checks the schema only. `run_pipeline` reads the files, fits the
sanity-check baselines, audits the run, and writes reports. A confirmed
`fail_on` violation writes a `FAILED` report and raises `ContractError`.
`censored_policy: reject` also writes a partial failed report with metrics null.
The training constant is a required reference model. Every leakage check must
be assigned to either `fail_on` or `warn_on`; moving a check to `warn_on` makes
its finding non-fatal but does not hide or downgrade its observed status.
The CLI commands `init`, `profile`, `check`, `train`, and `report` are explicit
stubs in v0.1; use `run_pipeline` for your own data.

The v0.1 schema rejects options that the runtime cannot yet honor. Static asset
features, native datetime parsing, frequency resampling, observation-bound
columns, a non-null prediction horizon, plot output, and Markdown reports are
deferred. Replacement episodes must use separate IDs, with
`replacement_starts_new_episode: true`. This prevents a configuration from
appearing to take effect when the pipeline would otherwise ignore it.

## Example report

Excerpt from an actual noisy-fleet run, omitting other fields:

```json
{
  "status": "COMPLETED",
  "headline_model": "hist_gradient_boosting",
  "headline_split": "test",
  "censored_or_unsupported_asset_ids": ["unit-censored"],
  "metrics": {
    "test": {
      "hist_gradient_boosting_root_mean_square_error": {
        "value": 1.9655398693652688,
        "status": "COMPUTED"
      }
    }
  }
}
```

Run status and leakage findings are separate. `COMPLETED` can include a
`WARNING`. Each finding names the check, evidence, and a remedy:

| Finding status | How to read it |
| --- | --- |
| `CONFIRMED` | A concrete violation was found; a configured `fail_on` check stops the run. |
| `WARNING` | A heuristic suggests investigation, such as high correlation with the label. |
| `NOT_CHECKED` | The check lacked data or did not run. This is not a pass. |
| `PASS` | The check ran and found no violation in its scope. |

The report records train/validation/test membership, training-only transformer
membership, excluded histories, model choice, and test confidence intervals.
A metric with no result has a null value and status `NOT_COMPUTED` or `DISABLED`;
it is never replaced with zero. Small splits warn; empty splits have no score.
See [audit coverage and limits](docs/leakage.md).

## FD001 benchmark

Use NASA's official C-MAPSS FD001 files:

```bash
rulsafe data fetch cmapss
rulsafe demo cmapss --output rulsafe-runs/cmapss
```

The fetch checks pinned hashes. Raw NASA files are not bundled or committed.
The headline evaluation scores the last observed cycle of each of the 100
official test engines against `RUL_FD001.txt`. The RUL cap is 125, seed 7,
and lookback 16, with last value, mean, and slope from records knowable at the
prediction time. Clipping and standard scaling fit only on the first 70
completed training engines. The next 15 supply validation and early stopping;
the remaining 15 supply a separate per-row test, not the official headline.
Test truth is never a training label or a model-selection input.

Fresh measurements at `cb1136e` with the committed locks:

| Model | Official test RMSE (cycles) | 95% RMSE interval | MAE (cycles) | NASA score |
| --- | ---: | ---: | ---: | ---: |
| Histogram gradient boosting | 16.6554 | 13.85–19.20 | 12.12 | 665.73 |
| Training-mean constant | 41.82 | 37.61–46.33 | 34.83 | 32028.68 |

Intervals resample engines. The NASA score sums one asymmetric term per engine;
it is not an average or a gate. Tree test metrics agree within `1e-9` across
Python 3.11.17, 3.12.15, and 3.13.17. All 141 tests passed with 91.48%
branch-inclusive coverage on each interpreter. These measurements describe
this protocol and dataset, not accuracy on other equipment. C-MAPSS is
simulated degradation data, not observations from a production fleet.

FD001's association check is `PASS` (strongest training |r| 0.808989 for
`sensor_17_mean`). Its delayed-record check is `NOT_CHECKED` because
`available_at` is absent. See the [verification record](benchmarks/verification-cb1136e.md)
and [source, protocol, hashes, and attribution](docs/cmapss-fd001.md).
The NASA catalog does not specify a dataset licence. The separate Zenodo
record's CC BY 4.0 statement applies to that record only.

An additional [physical NASA battery integration check](benchmarks/nasa-battery-smoke.md)
exercises the generic input path. Its small cell count limits it to a smoke
check; its scores are not a claim of battery-prediction accuracy.

## Development and release status

See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md), and
[SECURITY.md](SECURITY.md), and the [release review](docs/release-review-v0.1.0.md). The repository remains private pending owner
approval. No PyPI publication is part of release preparation.

Code licence: [Apache-2.0](LICENSE). Dataset terms remain separate.
