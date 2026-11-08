# Physical-data integration check: NASA milling tool wear

This is a **manual integration smoke check**, not an official benchmark or a
claim of tool-life prediction accuracy. It exercises the same generic CSV API
as user-supplied Readings and Events. There is no milling adapter or new label
task in the package, and default CI does not download the data.

## Source and prediction question

- [NASA PCoE Milling archive](https://phm-datasets.s3.amazonaws.com/NASA/3.+Milling.zip).
- Archive SHA-256 measured on 2026-11-08:
  `bdba8d52ec1a1baab24c2be58480e6ac62508c8cc1f8219f47ebde8fc9ebc474`.
- Nested `3. Milling/mill.zip` SHA-256:
  `de9c8685cb0e07b4f39459dc282b49192a3ad660e9577ff99b68dc9994e35d27`.
- Nested `mill.mat` SHA-256:
  `71486a857939d1416c86c7cf0c469d5e69c7c30495e01ec8a0e13aafd2a313cb`.
- The bundled source documentation identifies Kai Goebel (NASA Ames) and
  Alice Agogino (UC Berkeley), 16 physical milling cases, and 167 recorded
  cuts from a Matsuura MC-510V machining centre. It states that flank wear
  was measured after selected runs, at irregular intervals.
- No separate licence file was found in the downloaded archive. The raw and
  converted data are not redistributed by this repository.

The scenario event is the **first observed flank-wear measurement at or above
0.30 mm**. This is a user-defined maintenance threshold for this check. The
NASA source documentation does not declare it as an official failure criterion.
Missing wear measurements are never interpolated, so the event means first
*observed* threshold crossing. Later cuts are not used. Case 06 has one cut and
does not reach the threshold; it remains censored, named, and excluded.

The resulting 15 completed cases are partitioned in ascending case order:

| Role | Case IDs | Independent case count |
| --- | --- | ---: |
| Train | 01–05 and 07–12 | 11 |
| Validation | 13–14 | 2 |
| Test | 15–16 | 2 |
| Censored | 06 | 1 |

This is a fixed local split, not a NASA or literature protocol. The source
describes eight cutting settings repeated with a second set of inserts, all on
the same machining centre. It does not provide a physical parent identifier
that proves independence across every case. The split therefore tests pipeline
integration and cannot support a generalization claim.

## Causal features

Each Reading represents one completed cut. The script computes the mean and
root-mean-square of six supplied traces: AC and DC spindle current, table and
spindle vibration, and table and spindle acoustic emission. The source
documentation gives a 250 Hz rate for these processed signals. A Reading's
timestamp and `available_at` are its ordinal recorded-cut index. Lookback uses
only that cut and earlier completed cuts.
This generated `available_at` expresses the declared end-of-cut convention;
the source does not contain ingestion timestamps, so it cannot validate
real-world reporting delay.

**Measured flank wear, source run number, depth of cut, feed, material, and the
event record are not features.** The ordinal index is used because source run
numbers have gaps in some cases; the prediction question is remaining recorded
cuts until the observed threshold. Seed 7, lookback 16, train-only clipping and
scaling, the two existing baselines, and a null RUL cap are unchanged.

## Actual runs

Measured on 2026-11-08 with the committed per-interpreter dependency locks:

| Python | Selected model | Selected-model test RMSE | Test MAE | Test NASA sum | Tree test RMSE |
| --- | --- | ---: | ---: | ---: | ---: |
| 3.11.17 | Constant | 2.7271481351130276 | 2.525096525096525 | 0.9277325849191542 | 2.1221519236628468 |
| 3.12.15 | Constant | 2.7271481351130276 | 2.525096525096525 | 0.9277325849191542 | 2.1221519236628468 |
| 3.13.17 | Constant | 2.7271481351130276 | 2.525096525096525 | 0.9277325849191542 | 2.1221519236628468 |

Units are ordinal recorded cuts. Validation selected the constant baseline:
its validation RMSE was 2.29761524031969 on Python 3.11 and
2.2976152403196894 on Python 3.12/3.13, compared with tree validation RMSE
2.4108689392718867 and 2.4108689392718863 respectively. The tree happened to
score better on the two-case test, but the test result did not change the
selection. The tree kept 8 iterations.

All clean runs completed. Every configured `fail_on` finding passed. The
association check also passed: the strongest training association was
|r| 0.172273 for `smc_dc_mean_mean`, below 0.85. A separate planted run added
an innocently named `maintenance_index` equal to the target. It produced a
`FAILED` report with `target_in_features` `CONFIRMED` and the evidence
“Feature maintenance_index equals the training target on every scored row.”

Validation and test each contain only two cases and correctly retain
`split_below_minimum` warnings. Repeated cuts within a case are dependent and
do not increase the held-out equipment count. These measurements demonstrate
execution, causal conversion, censored-history handling, and leak detection;
they are not evidence of milling-model accuracy.

## Reproduce

From a locked development installation of this checkout:

```bash
curl -fL 'https://phm-datasets.s3.amazonaws.com/NASA/3.+Milling.zip' \
  -o /tmp/nasa-milling.zip
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python benchmarks/nasa_milling_smoke.py \
  /tmp/nasa-milling.zip --output rulsafe-runs/nasa-milling
```

The script verifies all three digests, reads the nested archive without
extracting it, writes local CSV inputs and exact partition files, saves
`run.yaml`, and writes `report.html`, `report.json`, and `summary.json`. SciPy
comes from the existing locked environment; no dependency is added. Raw data
and generated outputs stay outside git.
