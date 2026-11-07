"""C-MAPSS FD001 scoring at the last observation only.

The NASA catalog states that the objective is the remaining cycles after the
last cycle of each test engine. Scoring every test cycle is not the official
protocol. Training engines run until failure, so they do not exercise a
censored fleet label. A history that is neither a completed training
trajectory nor an official last-observation test engine is rejected or reported.
"""

from collections.abc import Sequence

from rulsafe.exceptions import not_implemented


def score_last_observation(
    *,
    predicted_remaining_cycles: Sequence[float],
    true_remaining_cycles: Sequence[float],
) -> dict[str, float]:
    """Score FD001 at the last observation of each test engine.

    Args:
        predicted_remaining_cycles: One prediction per test engine, in engine order.
        true_remaining_cycles: Official remaining cycles for those engines.

    Returns:
        Named scores. The NASA asymmetric score is part of the later implementation,
        copied from the dataset readme rather than from a blog.

    Raises:
        NotImplementedError: Last-observation scoring is not implemented yet.
    """
    raise not_implemented(
        "score_last_observation",
        predicted_remaining_cycles,
        true_remaining_cycles,
    )
