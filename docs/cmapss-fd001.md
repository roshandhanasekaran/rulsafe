# C-MAPSS FD001

v0.1 scores completed training trajectories from NASA C-MAPSS FD001. The raw archive is not part of this repository. `data/` is git-ignored.

## Source

The fetch command downloads the NASA Prognostics Data Repository zip:

https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip

That outer zip contains `CMAPSSData.zip`. The catalog page for the same data is [CMAPSS Jet Engine Simulated Data](https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data). The catalog page does not state a licence.

| File | SHA-256 |
| --- | --- |
| Outer Prognostics zip | `c9c5dec12a945a82e8bb4446589d7fb3cc057b5e5d81fa1a12e25ee9912ad3b2` |
| Inner `CMAPSSData.zip` | `74bef434a34db25c7bf72e668ea4cd52afe5f2cf8e44367c55a82bfd91a5a34f` |

`rulsafe data fetch cmapss` checks the outer hash, then the inner hash, and only then reads FD001. `rulsafe data fetch cmapss --from-file PATH` skips the download. `PATH` may be the outer zip or the inner `CMAPSSData.zip`. A file that matches neither pin is refused.

The inner archive contains `train_FD001.txt`, `test_FD001.txt`, `RUL_FD001.txt`, the same trio for FD002–FD004, `readme.txt`, and `Damage Propagation Modeling.pdf`. This converter reads only the FD001 trio.

## Licence and attribution

Licence: not specified on the NASA catalog page. Do not treat another deposit's licence as the catalog licence.

A separate Zenodo record, doi:10.5281/zenodo.15346912, states CC BY 4.0 for that record only. That statement is not the NASA catalog licence.

Cite Saxena, A. and Goebel, K. (2008). Turbofan Engine Degradation Simulation Data Set. NASA Ames Prognostics Data Repository. Also Saxena, Goebel, Simon and Eklund, Damage Propagation Modeling for Aircraft Engine Run-to-Failure Simulation, PHM 2008.

## What the FD001 demo scores

FD001 has 100 training engines and 100 test engines. Training engines run until failure. Test engines stop before failure.

Completed training engines are named `train-001` through `train-100` and split in unit-number order, without shuffling:

- train: the first 70, used to fit the model, the clip bounds, and the scaler
- validation: the next 15, used for early stopping and model selection
- test: the last 15, the secondary per-row view

Those id files are `data/cmapss/fd001_train_ids.txt`, `fd001_validation_ids.txt`, and `fd001_test_ids.txt`.

The headline evaluation is the official benchmark. It scores the last observed cycle of each NASA test engine (`test-001` through `test-100`) against `RUL_FD001.txt`. The converted file is `data/cmapss/fd001_official_rul.txt`, one `asset_id value` line per engine. That file is test truth. It is not a training label, and those engines are not in the training split.

Validation for the same protocol is the last pre-failure cycle of the 15 held-out training engines. Early stopping still uses every causal row of those engines and does not read the RUL file. The per-row scores on the 15 held-out training engines in `fd001_test_ids.txt` are reported as `secondary_evaluation`. They are not the official benchmark.

`target.rul_cap` is 125 in the example. Every supervised target and every official truth is `min(remaining life, 125)` before fit and score. The report states the cap. A generic run leaves `target.rul_cap` null.

The NASA score is the Saxena 2008 sum of one term per engine. It is not summed over rows, and it is not a gate. Test RMSE and MAE also have a percentile bootstrap over engines.

The NASA test engines are still written as censored histories so they stay out of training. `censored_policy: report` lists them.

The converted tables are:

- `data/cmapss/fd001_assets.parquet`
- `data/cmapss/fd001_signals.parquet`
- `data/cmapss/fd001_events.parquet`
- `data/cmapss/fd001_official_rul.txt`

Signal features are the three operational settings and the 21 sensors, plus a causal mean and slope over `windows.lookback` past rows. Clip percentiles and the standard scaler are fit on the training rows only. The unit id and the cycle are not features.

```bash
rulsafe data fetch cmapss
rulsafe demo cmapss --output ./rulsafe-runs/cmapss
```

From a local copy of either pinned zip:

```bash
rulsafe data fetch cmapss --from-file /path/to/CMAPSSData.zip
```
