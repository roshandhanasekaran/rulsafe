# RULSafe

v0.1 is a completed-trajectory remaining-useful-life research toolkit. Point it at local CSV or Parquet files, build causal features, keep train, validation, and final test apart, fit a constant baseline and one tree model on the training split, and write an audit.

The audit lists every check. A check that did not run is `NOT_CHECKED`. It is not a pass, and the report must not say the data are free of leakage.

`censored_policy: reject` writes a partial report with status `FAILED` and no metrics, then stops the run. `report` excludes the history from every split, continues, and names it. Histories are not dropped quietly. SCANIA Component X is a censored fleet and is v0.2. The v0.1 demo is C-MAPSS FD001. Its headline score is the last observation of each official test engine against `RUL_FD001.txt`. Held-out training engines supply validation, and their per-row scores are a secondary view. That demo does not exercise a live fleet's censored vehicles. The report says so. `report.html` is written next to `report.json`.

This package is not a safety-certified prognostic.

## Related work

**CeRULEo** is a toolkit of remaining-useful-life methods. Lorenti and Susto, *Journal of Open Source Software* 8(88), 5294 (2023), [doi:10.21105/joss.05294](https://doi.org/10.21105/joss.05294). Code: [lucianolorenti/ceruleo](https://github.com/lucianolorenti/ceruleo), MIT. It trains and compares RUL methods once a table exists. It does not enforce this package's data contract or the rule that an unscored history must be rejected or reported.

**RTX Providence** is a neural time-to-event research framework. Fox, Zimmerman, Daly, O'Keeffe and Verleyen, IEEE Aerospace Conference 2022, [doi:10.1109/AERO53065.2022.9843469](https://doi.org/10.1109/AERO53065.2022.9843469). Code: [rtx-corp-open-source/providence](https://github.com/rtx-corp-open-source/providence). The GitHub API reports the licence as Other / `NOASSERTION`. Do not invent an SPDX identifier; read `LICENSE_AND_REQUIRED_MARKING.rst` before depending on it. Providence models time-to-event. It does not provide this package's causal-window and coverage audit.

## Layout

C-MAPSS FD001 is fetched, not bundled. The source URL, both SHA-256 pins, and the censored-test rule are in [C-MAPSS FD001](cmapss-fd001.md).

The implementation lives under `src/rulsafe/`. Commands that are not built yet raise `NotImplementedError` and the command line exits with code 2. See the leakage note for statuses and the v0.1 check list. The supply-chain decision, still proposed, is [ADR-010](decisions/ADR-010-security-supply-chain.md).
