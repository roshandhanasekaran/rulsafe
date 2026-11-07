"""Tree metrics that must agree on Python 3.11, 3.12, and 3.13.

The reference is the synthetic panel after near-constant columns are centered
and left on a scale of 1. The same run was measured on each supported
interpreter. Absolute differences above the stated tolerance fail this test.
"""

import warnings

import pytest

from rulsafe import run_pipeline
from rulsafe.config import RunConfig

# Stated absolute tolerance for RMSE, MAE, and the NASA score.
STATED_ABSOLUTE_TOLERANCE = 1e-6

# Measured on Python 3.11.18, 3.12.3, and 3.13.18. The three runs matched.
REFERENCE_TREE_TEST = {
    "root_mean_square_error": 0.00739044155925539,
    "mean_absolute_error": 0.00739044155925539,
    "nasa_score": 0.0007393173163461331,
}


def test_panel_tree_metrics_match_the_cross_version_reference(load_example, tmp_path) -> None:
    """The panel tree stays within 1e-6 of the shared reference."""
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        document = run_pipeline(config, output_directory=tmp_path).to_dict()
    metrics = document["metrics"]
    assert isinstance(metrics, dict)
    test_metrics = metrics["test"]
    assert isinstance(test_metrics, dict)
    for suffix, expected in REFERENCE_TREE_TEST.items():
        metric = test_metrics[f"hist_gradient_boosting_{suffix}"]
        assert isinstance(metric, dict)
        assert metric["status"] == "COMPUTED"
        assert metric["value"] == pytest.approx(expected, abs=STATED_ABSOLUTE_TOLERANCE)
    assert document["hist_gradient_boosting_iteration_count"] == 40
