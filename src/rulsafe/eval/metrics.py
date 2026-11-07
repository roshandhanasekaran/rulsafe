"""Remaining-life scores by split.

v0.1 reports validation and, after the headline model is frozen, the final
test. Official C-MAPSS numbers use the last observation of each test engine
only. Scoring every test cycle is not the official protocol.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from rulsafe.exceptions import not_implemented
from rulsafe.report.json import MetricValue


@dataclass(frozen=True)
class SplitMetrics:
    """Named scores for one split.

    Attributes:
        values: Metric name to a :class:`MetricValue`. Disabled and uncomputed
            scores keep a null value and an explicit status.
    """

    values: Mapping[str, MetricValue]


@dataclass(frozen=True)
class MetricsReport:
    """Validation scores and the frozen final-test scores.

    Attributes:
        validation: Scores used to choose the headline model.
        test: Scores computed after that choice is frozen.
    """

    validation: SplitMetrics
    test: SplitMetrics


def score_remaining_life(
    *,
    predicted: Mapping[str, float],
    actual: Mapping[str, float],
    split_name: str,
) -> SplitMetrics:
    """Score remaining life on one split.

    Args:
        predicted: Predicted remaining life by entity or window identifier.
        actual: Actual remaining life for the same identifiers.
        split_name: ``train``, ``validation``, or ``test``.

    Returns:
        Named error summaries for the split.

    Raises:
        NotImplementedError: Scoring is not implemented yet.
    """
    raise not_implemented("score_remaining_life", predicted, actual, split_name)
