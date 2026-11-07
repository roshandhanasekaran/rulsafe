# RULSafe

RULSafe is a local, leakage-safe **completed-trajectory remaining-useful-life research toolkit**. v0.1 prepares causal training rows for one question — how much life remains on a trajectory that runs to a known end — and writes an audit whose coverage is explicit.

It is a Python package and a command-line tool. It is not a web application. It is research and decision-support software, **not a safety-certified prognostic**, and a finished audit is not a guarantee that every leak was found.

v0.1 does not silently drop a history it cannot score. A censored or unsupported history is **rejected or reported**. SCANIA Component X, the censored heavy-truck fleet, is **v0.2**. The v0.1 demo is **C-MAPSS FD001**, scored at the last observation of each test engine, together with small synthetic fixtures.

## Install

Python 3.10 or newer:

```bash
pip install -e ".[dev]"
```

`[demo]` adds Jinja2 for the later HTML report. Matplotlib is intentionally not pinned yet: current Matplotlib releases do not support the whole 3.10–3.13 range this foundation tests.

## What works in this foundation

This release is the repository foundation. The schema, the history-disposition rule, dataset cards, and the command-line skeleton are real. Training, windowing, downloads, and report writing are specified and not implemented yet.

```bash
rulsafe --help
rulsafe --version
rulsafe validate --config examples/cmapss_fd001_completed_trajectory.yaml
rulsafe datasets list
```

`datasets list` prints access and licence as separate facts. For C-MAPSS the NASA catalog licence is **not specified**. A separate Zenodo record (doi:10.5281/zenodo.15346912) states CC BY 4.0 for that record only. Those statements are not merged. SCANIA is listed as v0.2 under CC BY 4.0 and is not downloaded.

`rulsafe validate` checks the YAML contract only. It does not open the data files.

Run the synthetic completed-trajectory demo from the repository root. It writes `report.json`. `engine_e` is censored and stays in that report. The constant baseline is fit on the training split only. The tree baseline is `NOT_COMPUTED`.

```bash
rulsafe demo synthetic --output ./rulsafe-runs/synthetic
```

These commands exist and exit with code 2 until the rest of the pipeline exists:

```bash
rulsafe demo cmapss --output ./rulsafe-runs/demo
rulsafe check --config examples/cmapss_fd001_completed_trajectory.yaml
rulsafe train --config examples/cmapss_fd001_completed_trajectory.yaml
```

`rulsafe demo scania` is refused. There is no `rulsafe ui` command.

## Usage

### Command line

Validate a completed-trajectory configuration. This does not read the data files:

```bash
rulsafe validate --config examples/cmapss_fd001_completed_trajectory.yaml
rulsafe validate --config examples/synthetic_panel.yaml
```

A SCANIA configuration is rejected in v0.1:

```bash
rulsafe validate --config examples/scania_component_x.yaml
```

List datasets. Access and licence are separate lines. C-MAPSS prints "not specified" for the NASA catalog, then the Zenodo note. SCANIA prints CC BY 4.0 and is marked v0.2:

```bash
rulsafe datasets list
rulsafe datasets fetch cmapss_fd001
rulsafe datasets fetch scania_component_x
```

`fetch` prints the card and then stops. The download is not implemented. The SCANIA fetch stops because that dataset is v0.2.

Exit codes once the pipeline exists: `0` finished with no confirmed `fail_on` finding, `1` confirmed leakage, `2` usage or configuration error. In this foundation, unfinished commands use `2`.

### Python

```python
from rulsafe import load_config, run_pipeline
from rulsafe.report.json import MetricValue

config = load_config("examples/cmapss_fd001_completed_trajectory.yaml")
config.project.name
config.labeling.censored_policy.value  # "reject" or "report"

# The pipeline is specified and not implemented in this foundation.
# result = run_pipeline(config, output_directory=Path("rulsafe-runs/demo"))

MetricValue.disabled().to_json()
# {"value": null, "status": "DISABLED"}

MetricValue.not_computed().to_json()
# {"value": null, "status": "NOT_COMPUTED"}

MetricValue.computed(12.5).to_json()
# {"value": 12.5, "status": "COMPUTED"}
```

`run_pipeline` raises `NotImplementedError` until training exists. Call `load_config` or `RunConfig.from_mapping` to validate a mapping without YAML. A disabled metric was not requested. A not-computed metric is in scope but has no number. Neither is stored as `0`.

## v0.1 contract

- **Question.** Remaining useful life on a completed trajectory. C-MAPSS test engines are scored at the **last observation** only.
- **Splits.** `official_partitions` or `group_holdout`. Train, validation, and final test stay apart. A random panel split is an error. `global_time` is rejected: it is deferred to v0.2. The headline model is chosen on validation.
- **Features.** At time `t`, a feature uses only records knowable at `t`. The default gap policy is `none`. Bounded forward fill is allowed. Linear interpolation is rejected.
- **Preprocessing.** Clip bounds and scalers fit on the training split only, with a membership record.
- **Baselines.** A training constant, and one histogram gradient boosting model. Persistence is rejected. Age and logistic regression are not in v0.1.
- **Censored histories.** `censored_policy` is `reject` or `report`. `drop` and `unknown_policy: exclude_from_loss` are errors.
- **Audit.** Statuses are `CONFIRMED`, `WARNING`, `NOT_CHECKED`, and `PASS`. A check with no finding is reported as `NOT_CHECKED`, not as a pass. A metric with no number serialises as `{"value": null, "status": "NOT_COMPUTED"}` or `{"value": null, "status": "DISABLED"}`. It is not stored as zero.
- **Not in v0.1.** `global_time` and `alerts` are rejected with an error that they are deferred to v0.2. They are not dropped silently.

## Roadmap

**Still required before v0.1 can be called complete**

- Causal windows, labels, and the three splitters, with synthetic fixtures under `tests/fixtures/synthetic_panel/`
- Train-only preprocessing and the two baselines
- Leakage checks with a planted failure and a clean pass for each `fail_on` id
- Last-observation C-MAPSS scoring, including the NASA score from the dataset readme
- HTML, JSON, and a Rich terminal summary, with documented coverage
- `rulsafe demo cmapss` writing `report.html` and `report.json`
- Invariance tests: future rows do not change earlier features; final-test labels do not move the fitted model or the validation choice

**v0.2 and later, only if the completed-trajectory toolkit is in use**

- SCANIA Component X under its official protocol (105 signal columns, CC BY 4.0 printed separately, no reconstructed hidden time-to-event on the official validation and test sets)
- Censored fleet labels: positive, negative, and unknown, kept in the export
- `global_time` splits
- Fleet alert metrics: event recall, lead time, false alerts per asset-time
- Optional industry datasets. They are not a v0.1 benchmark harness.

Out of scope until someone asks: a user interface, warehouse connectors, Chronos, AutoGluon, and publishing to PyPI.

## Related work

[CeRULEo](https://github.com/lucianolorenti/ceruleo) (Lorenti and Susto, *Journal of Open Source Software* 8(88), 5294, 2023, [doi:10.21105/joss.05294](https://doi.org/10.21105/joss.05294)) is a toolkit of remaining-useful-life methods. [RTX Providence](https://github.com/rtx-corp-open-source/providence) (Fox, Zimmerman, Daly, O'Keeffe and Verleyen, IEEE Aerospace Conference 2022, [doi:10.1109/AERO53065.2022.9843469](https://doi.org/10.1109/AERO53065.2022.9843469)) is a neural time-to-event research framework. The GitHub API reports Providence's licence as Other / `NOASSERTION`; this project does not assign it an SPDX identifier.

Neither package is this audit. v0.1's leftover is causal windows, a named train / validation / test protocol, training-only preprocessing, and an explicit disposition for histories it cannot score.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). The short path:

```bash
pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
ruff check .
mypy src
pytest
```

Licence: Apache-2.0. Dataset licences stay with the dataset owners. The wheel does not contain third-party data files.
