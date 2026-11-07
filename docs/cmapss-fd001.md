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

## What v0.1 keeps

FD001 has 100 training engines and 100 test engines. Training engines run until failure. Test engines stop before failure.

v0.1 uses the completed training engines only. They are named `train-001` through `train-100` and split in unit-number order, without shuffling:

- train: the first 70
- validation: the next 15
- test: the last 15

Those id files are `data/cmapss/fd001_train_ids.txt`, `fd001_validation_ids.txt`, and `fd001_test_ids.txt`. The example config reads them as `official_partitions`.

The NASA test engines are written as censored histories (`test-001` through `test-100`) with event type `censored`. `censored_policy: report` lists them and leaves them out of every split. They are not training rows. `RUL_FD001.txt` is checked so the archive is recognisable, and its values are not copied into labels or features. Reconstructing those hidden remaining-life values is out of scope for this demo.

The converted tables are:

- `data/cmapss/fd001_assets.parquet`
- `data/cmapss/fd001_signals.parquet`
- `data/cmapss/fd001_events.parquet`

Signal features are the three operational settings and the 21 sensors. The unit id and the cycle are not features.

```bash
rulsafe data fetch cmapss
rulsafe demo cmapss --output ./rulsafe-runs/cmapss
```

From a local copy of either pinned zip:

```bash
rulsafe data fetch cmapss --from-file /path/to/CMAPSSData.zip
```
