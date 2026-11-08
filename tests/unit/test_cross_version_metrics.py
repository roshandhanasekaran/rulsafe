"""Tree metrics that must agree on Python 3.11, 3.12, and 3.13.

The reference is the noisy demo fleet, not the degenerate unit smoke panel.
See benchmarks/verification-cb1136e.md for the independently measured runs.
Absolute differences above the stated tolerance fail this test.
"""

import pytest

from rulsafe import run_pipeline
from rulsafe.config import RunConfig

# Stated absolute tolerance for RMSE, MAE, and the NASA score.
STATED_ABSOLUTE_TOLERANCE = 1e-6

# Measured on Python 3.11.17, 3.12.15, and 3.13.17. The three runs matched.
REFERENCE_TREE_TEST = {
    "root_mean_square_error": 1.9655398693652688,
    "mean_absolute_error": 1.2852426319239971,
    "nasa_score": 0.15571061547349063,
}


def test_fleet_tree_metrics_match_the_cross_version_reference(load_example, tmp_path) -> None:
    """The noisy demo tree stays within 1e-6 of the shared reference."""
    config = RunConfig.from_mapping(load_example("synthetic_fleet.yaml"))
    document = run_pipeline(config, output_directory=tmp_path).to_dict()
    metrics = document["metrics"]
    assert isinstance(metrics, dict)
    test_metrics = metrics["test"]
    assert isinstance(test_metrics, dict)
    for suffix, expected in REFERENCE_TREE_TEST.items():
        metric = test_metrics[f"hist_gradient_boosting_{suffix}"]
        assert isinstance(metric, dict)
        assert metric["status"] == "COMPUTED"
        assert metric["value"] == pytest.approx(expected, rel=0, abs=STATED_ABSOLUTE_TOLERANCE)
    assert document["hist_gradient_boosting_iteration_count"] == 39
