# Physical-data integration check: NASA Li-ion batteries

This is a **manual integration smoke check**, not an official benchmark or a
claim of battery prediction accuracy. It exercises the same generic CSV API
as user-supplied Readings and Events. There is no new battery adapter or label
task. Default CI does not download it.

## Source and labels

- [NASA Li-ion battery aging catalog](https://data.nasa.gov/dataset/li-ion-battery-aging-datasets).
- [NASA Prognostics archive](https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip).
- Archive SHA-256 measured on 2026-11-08:
  `82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e`.
  This is a digest of the downloaded source, not a NASA signature.
- Only `1. BatteryAgingARC-FY08Q4.zip` and its B0005, B0006, B0007, B0018
  MAT files are read. Its README defines end-of-life as capacity fading from
  2 Ah to 1.4 Ah. The catalog licence is **not specified**; no raw/converted
  data are redistributed by this repository.

The event is the first observed discharge whose measured capacity is at most
1.4 Ah. This is a capacity-defined **end-of-life event**, not an inferred
catastrophic battery failure. Later discharges are not used. The physical
observations give:

| Cell | Observed discharges | First qualifying EOL discharge | Disposition |
| --- | ---: | ---: | --- |
| B0005 | 168 | 125 | Train |
| B0006 | 168 | 109 | Validation |
| B0007 | 168 | Not observed | Censored; excluded and named |
| B0018 | 132 | 97 | Test |

The fixed split follows ascending completed-cell ID. It is **not** a NASA
split. `official_partitions` is the configuration's mechanism for supplying
these fixed ID files; its name does not make this a sanctioned protocol.
The prediction question is remaining discharge cycles until this EOL event.

Each Reading contains the mean measured voltage, current, and temperature
from a completed discharge. Its timestamp and `available_at` are that
completed-discharge index. The summaries are knowable then; lookback uses
only those and earlier completed cycles. **Capacity and discharge duration
are never features.** Treating whole-discharge summaries as available at the
start of a discharge would be leakage and is not the convention used here.

Seed 7, lookback 16, train-only clipping/scaling, and the existing baseline
settings are unchanged. The RUL cap is null. No model settings or split were
tuned on the test cell.

## Actual runs

Measured on 2026-11-08 with the committed per-interpreter dependency locks:

| Python | Tree test RMSE (cycles) | Tree test MAE | Tree NASA sum | Constant test RMSE |
| --- | ---: | ---: | ---: | ---: |
| 3.11.17 | 12.43840298117819 | 10.535867796796483 | 18.497997843003706 | 31.047007370544858 |
| 3.12.15 | 12.43840298117819 | 10.53586779679649 | 18.497997843003706 | 31.047007370544858 |
| 3.13.17 | 12.43840298117819 | 10.53586779679649 | 18.497997843003706 | 31.047007370544858 |

All runs complete and write HTML/JSON. The tree keeps 22 iterations.
All configured `fail_on` findings pass. `high_association_with_label` warns:
training voltage has |r| 0.907914, above 0.85. The generated `available_at`
reflects the declared end-of-discharge convention, not source ingestion logs;
a pass on delayed-record leakage does not validate real-world reporting delay.

**Every split has only one independent completed cell**, so all three splits
correctly retain `split_below_minimum` warnings. The many readings within a
cell are not independent held-out machines. An engine/cell bootstrap with
one test cell cannot estimate between-cell uncertainty. These metrics are
recorded to make execution reproducible, not to advertise generalization.
A larger independent physical dataset and a predeclared domain protocol are
needed for a performance claim.

## Reproduce

From a locked development installation of this checkout:

```bash
curl -fL 'https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip' \
  -o /tmp/nasa-battery.zip
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python benchmarks/nasa_battery_smoke.py \
  /tmp/nasa-battery.zip --output rulsafe-runs/nasa-battery
```

The script verifies the digest before converting, writes CSV inputs, saves the
exact config as `run.yaml`, then writes `report.html`, `report.json`, and a
compact `summary.json` under the chosen output directory. SciPy comes from
the existing development locks. No new runtime dependency is added. Raw data
and generated outputs stay outside git.
