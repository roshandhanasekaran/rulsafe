"""Percentile bootstrap of test error over engines.

Engines are drawn with replacement. Every scored row of a drawn engine is
kept, so a per-row test does not treat two rows from one engine as two
independent engines. The point is the full-sample score. The interval is
the percentile interval of the bootstrap samples. The project seed drives
``random.Random``.
"""

import math
import random
from collections.abc import Sequence

from rulsafe.eval.metrics import mean_absolute_error, root_mean_square_error
from rulsafe.exceptions import ContractError

BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_LEVEL = 0.95
BOOTSTRAP_METHOD = "percentile bootstrap over engines"


def bootstrap_engine_intervals(
    *,
    asset_ids: Sequence[str],
    actual: Sequence[float],
    predicted: Sequence[float],
    seed: int,
    samples: int = BOOTSTRAP_SAMPLES,
    level: float = BOOTSTRAP_LEVEL,
) -> dict[str, object]:
    """Return engine-level confidence intervals for RMSE and MAE.

    Args:
        asset_ids: Engine id of each scored row.
        actual: Observed remaining life, in the same order.
        predicted: Predicted remaining life, in the same order.
        seed: Project seed.
        samples: Number of bootstrap draws.
        level: Interval level, such as 0.95.

    Returns:
        Engine count plus ``point``, ``lower``, and ``upper`` for
        root-mean-square error and mean absolute error.

    Raises:
        ContractError: The sequences differ in length or are empty, or the
            bootstrap settings are not usable.
    """
    if samples < 1:
        raise ContractError("Bootstrap samples must be at least 1.")
    if not 0.0 < level < 1.0:
        raise ContractError("Bootstrap level must be strictly between 0 and 1.")
    if not (len(asset_ids) == len(actual) == len(predicted)):
        raise ContractError("Bootstrap inputs must have the same length.")
    if not asset_ids:
        raise ContractError("Bootstrap needs at least one scored row.")
    grouped: dict[str, list[tuple[float, float]]] = {}
    engines: list[str] = []
    for asset_id, truth, guess in zip(asset_ids, actual, predicted, strict=True):
        if asset_id not in grouped:
            engines.append(asset_id)
            grouped[asset_id] = []
        grouped[asset_id].append((float(truth), float(guess)))
    point_rmse = root_mean_square_error(actual, predicted)
    point_mae = mean_absolute_error(actual, predicted)
    # The project seed makes the interval repeatable. It is not a secret.
    generator = random.Random(seed)  # noqa: S311  # nosec B311
    rmse_samples: list[float] = []
    mae_samples: list[float] = []
    engine_count = len(engines)
    for _ in range(samples):
        drawn_actual: list[float] = []
        drawn_predicted: list[float] = []
        for _draw in range(engine_count):
            asset_id = engines[generator.randrange(engine_count)]
            for truth, guess in grouped[asset_id]:
                drawn_actual.append(truth)
                drawn_predicted.append(guess)
        rmse_samples.append(root_mean_square_error(drawn_actual, drawn_predicted))
        mae_samples.append(mean_absolute_error(drawn_actual, drawn_predicted))
    return {
        "engine_count": engine_count,
        "root_mean_square_error": _bounds(point_rmse, rmse_samples, level),
        "mean_absolute_error": _bounds(point_mae, mae_samples, level),
    }


def _bounds(point: float, samples: Sequence[float], level: float) -> dict[str, float]:
    """Build one percentile interval around the full-sample point.

    Args:
        point: Full-sample score.
        samples: Bootstrap scores.
        level: Interval level.

    Returns:
        Point, lower, and upper.
    """
    tail = (1.0 - level) / 2.0
    return {
        "point": point,
        "lower": _percentile(samples, tail),
        "upper": _percentile(samples, 1.0 - tail),
    }


def _percentile(values: Sequence[float], quantile: float) -> float:
    """Return a linearly interpolated percentile of a bootstrap sample.

    Args:
        values: Sample values.
        quantile: Quantile between 0 and 1.

    Returns:
        The interpolated value.
    """
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight
