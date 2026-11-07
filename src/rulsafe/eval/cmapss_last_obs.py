"""C-MAPSS FD001 scoring at the last observation only.

The NASA catalog states that the objective is the remaining cycles after the
last cycle of each test engine. Scoring every test cycle is not the official
protocol. Root-mean-square error and mean absolute error are primary. The
NASA asymmetric score is reported and is not a gate. Training engines run
until failure, so they do not exercise a censored fleet label. A history
that is neither a completed training trajectory nor an official
last-observation test engine is rejected or reported.
"""

from collections.abc import Sequence

from rulsafe.eval.metrics import (
    mean_absolute_error,
    nasa_asymmetric_score,
    root_mean_square_error,
)
from rulsafe.exceptions import ContractError


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
        Root-mean-square error, mean absolute error, and the NASA score from
        Saxena, Goebel, Simon and Eklund, PHM 2008. The NASA score is not a gate.

    Raises:
        ContractError: The two sequences differ in length or are empty.
    """
    if len(predicted_remaining_cycles) != len(true_remaining_cycles):
        raise ContractError("Last-observation predictions and labels must have the same length.")
    if not predicted_remaining_cycles:
        raise ContractError("Last-observation scoring needs at least one engine.")
    return {
        "root_mean_square_error": root_mean_square_error(
            true_remaining_cycles, predicted_remaining_cycles
        ),
        "mean_absolute_error": mean_absolute_error(
            true_remaining_cycles, predicted_remaining_cycles
        ),
        "nasa_score": nasa_asymmetric_score(true_remaining_cycles, predicted_remaining_cycles),
    }
