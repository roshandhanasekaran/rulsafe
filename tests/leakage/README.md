# Leakage tests

`test_pipeline_guards.py` is part of the default suite. It checks that test labels and test features do not move the fit, that a future row does not change earlier features, and that fit rows come from train assets only. Each `fail_on` check still needs a planted failure that returns `CONFIRMED` with evidence, and a clean fixture that does not.
