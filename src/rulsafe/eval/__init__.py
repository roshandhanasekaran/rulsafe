"""Evaluation of a frozen completed-trajectory model.

Fleet alert metrics are reported as not covered in v0.1.
"""

from rulsafe.eval.alerts import fleet_alert_coverage as fleet_alert_coverage
from rulsafe.eval.cmapss_last_obs import score_last_observation as score_last_observation
from rulsafe.eval.metrics import MetricsReport as MetricsReport
from rulsafe.eval.metrics import score_remaining_life as score_remaining_life

__all__ = [
    "MetricsReport",
    "fleet_alert_coverage",
    "score_last_observation",
    "score_remaining_life",
]
