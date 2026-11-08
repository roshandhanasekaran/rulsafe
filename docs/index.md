# RULSafe documentation

RULSafe checks failure-prediction data before model development. v0.1 supports
completed-trajectory remaining useful life with local Readings, Events, and
an Assets list. The [README quickstart](../README.md#quickstart) includes the
column map and an executable Python example.

- [Leakage audit](leakage.md): findings, coverage, causal windows, and limits.
- [C-MAPSS FD001](cmapss-fd001.md): official protocol, source hashes, and attribution.
- [Independent verification](../benchmarks/verification-cb1136e.md): actual
  measurements across the supported Python versions.
- [Contributing](../CONTRIBUTING.md): locked setup, tests, and review procedure.
- [Security](../SECURITY.md) and [supply-chain decision](decisions/ADR-010-security-supply-chain.md).
- [Release preparation](releasing.md) and [critical review](release-review-v0.1.0.md).
- [Changelog](../CHANGELOG.md): release scope and unimplemented features.

Failure-within-horizon questions and censored-fleet classification are deferred.
A completed report is not a declaration that a dataset is free of leakage.
