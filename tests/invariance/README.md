# Invariance tests

The release gates live in `tests/leakage/test_pipeline_guards.py` and run with the default suite:

1. Appending a record after time `t` does not change features at `t`.
2. Relabelling the test split, or perturbing its features, does not change the fit, the iteration count, or the model choice.
3. Fit rows come from train assets only.
