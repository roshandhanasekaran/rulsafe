"""Evaluation of a frozen completed-trajectory model.

Fleet alerts are deferred to v0.2 and rejected in configuration.
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
