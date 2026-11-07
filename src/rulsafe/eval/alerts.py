"""Fleet alert metrics.

Alert cadence, lead time, and false alerts per asset-time are a fleet
question. They are not a v0.1 headline. A v0.1 report that is asked for
them must say they are not covered. It must not omit the request.
"""

from rulsafe.exceptions import not_implemented

FLEET_ALERT_COVERAGE = "not_covered"


def fleet_alert_coverage() -> str:
    """Return how v0.1 reports fleet alert metrics.

    Returns:
        ``not_covered``. This is not a pass and not a silent omission.
    """
    return FLEET_ALERT_COVERAGE


def evaluate_alerts(*, horizon: int, cooldown: str | int) -> dict[str, float]:
    """Evaluate event recall, lead time, and false alerts.

    Args:
        horizon: Label horizon the alerter would use.
        cooldown: ``horizon`` or a non-negative step count.

    Returns:
        Alert counts and rates.

    Raises:
        NotImplementedError: Fleet alert evaluation is not part of v0.1.
    """
    raise not_implemented("evaluate_alerts", horizon, cooldown)
