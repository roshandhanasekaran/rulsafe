# Leakage tests

`test_pipeline_guards.py` checks that test labels and test features do not move the fit, that a future row does not change earlier features, and that fit rows come from train assets only. `test_fail_on_fixtures.py` plants a `CONFIRMED` case and a clean `PASS` control for every `fail_on` check.
