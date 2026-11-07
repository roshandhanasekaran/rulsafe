"""Remaining-life scores by split.

Validation scores are used for early stopping and for choosing the model.
That choice is optimistic, so the headline evaluation is the final test of
the selected model. Root-mean-square error and mean absolute error are the
primary scores. The NASA asymmetric score is secondary: it is reported and
it never chooses the model or fails a run. Official C-MAPSS numbers use the
last observation of each test engine only.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rulsafe.config import BaselineName
from rulsafe.exceptions import ContractError
from rulsafe.report.json import MetricComputationStatus, MetricValue

# PHM 2008 / C-MAPSS asymmetric score. d = estimated RUL - true RUL.
# Early predictions (d < 0) use 13. Late predictions use 10 and cost more.
_NASA_EARLY_DIVISOR = 13.0
_NASA_LATE_DIVISOR = 10.0
_SPLIT_NAMES = frozenset({"train", "validation", "test"})
METRIC_SUFFIXES: tuple[str, ...] = (
    "root_mean_square_error",
    "mean_absolute_error",
    "nasa_score",
)


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
        validation: Scores used for early stopping and model selection.
        test: Headline evaluation, computed after that choice is frozen.
    """

    validation: SplitMetrics
    test: SplitMetrics


def root_mean_square_error(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Return the root-mean-square error of paired remaining-life values.

    Args:
        actual: Observed remaining life, in row order.
        predicted: Predicted remaining life, in the same order.

    Returns:
        The non-negative root-mean-square error.

    Raises:
        ContractError: The sequences differ in length or are empty.
    """
    pairs = _pairs(actual, predicted)
    mean_square = sum((guess - truth) ** 2 for truth, guess in pairs) / len(pairs)
    return float(mean_square**0.5)


def mean_absolute_error(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Return the mean absolute error of paired remaining-life values.

    Args:
        actual: Observed remaining life, in row order.
        predicted: Predicted remaining life, in the same order.

    Returns:
        The non-negative mean absolute error.

    Raises:
        ContractError: The sequences differ in length or are empty.
    """
    pairs = _pairs(actual, predicted)
    return sum(abs(guess - truth) for truth, guess in pairs) / len(pairs)


def nasa_asymmetric_score(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Return the PHM 2008 asymmetric score for the pairs it is given.

    ``d`` is estimated remaining life minus true remaining life. A negative
    ``d`` (early) contributes ``exp(-d / 13) - 1``. A non-negative ``d``
    (late) contributes ``exp(d / 10) - 1``. The result is the sum of those
    terms. The Saxena 2008 engine score passes one pair per engine, not one
    pair per row. The score is not a gate and it does not choose the headline
    model.

    Args:
        actual: Observed remaining life, in row order.
        predicted: Predicted remaining life, in the same order.

    Returns:
        The summed asymmetric score. Zero means a perfect prediction.

    Raises:
        ContractError: The sequences differ in length or are empty.
    """
    total = 0.0
    for truth, guess in _pairs(actual, predicted):
        difference = guess - truth
        if difference < 0:
            total += math.exp(-difference / _NASA_EARLY_DIVISOR) - 1.0
        else:
            total += math.exp(difference / _NASA_LATE_DIVISOR) - 1.0
    return total


def last_observation_pairs(
    asset_ids: Sequence[str],
    times: Sequence[float],
    actual: Sequence[float],
    predicted: Sequence[float],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Keep the last scored time of each engine.

    Args:
        asset_ids: Engine id of each row.
        times: Prediction time of each row.
        actual: Observed remaining life.
        predicted: Predicted remaining life.

    Returns:
        Actual and predicted values, one pair per engine, in asset-id order.
        When two rows share a time, the later row is kept.

    Raises:
        ContractError: The sequences differ in length or are empty.
    """
    if not (len(asset_ids) == len(times) == len(actual) == len(predicted)):
        raise ContractError("Per-engine pairs need sequences of the same length.")
    if not asset_ids:
        raise ContractError("Per-engine scoring needs at least one row.")
    best: dict[str, tuple[float, int, float, float]] = {}
    for index, (asset_id, time, truth, guess) in enumerate(
        zip(asset_ids, times, actual, predicted, strict=True)
    ):
        current = best.get(asset_id)
        if current is None or time > current[0] or (time == current[0] and index >= current[1]):
            best[asset_id] = (time, index, float(truth), float(guess))
    ordered = [best[asset_id] for asset_id in sorted(best)]
    return tuple(item[2] for item in ordered), tuple(item[3] for item in ordered)


def score_with_per_engine_nasa(
    *,
    asset_ids: Sequence[str],
    times: Sequence[float],
    actual: Sequence[float],
    predicted: Sequence[float],
) -> dict[str, MetricValue]:
    """Score rows with RMSE and MAE, and the NASA score once per engine.

    Root-mean-square error and mean absolute error use every row. The NASA
    score uses the last scored time of each engine and then sums those terms.

    Args:
        asset_ids: Engine id of each row.
        times: Prediction time of each row.
        actual: Observed remaining life.
        predicted: Predicted remaining life.

    Returns:
        Three computed metrics.
    """
    unit_actual, unit_predicted = last_observation_pairs(asset_ids, times, actual, predicted)
    return {
        "root_mean_square_error": MetricValue.computed(root_mean_square_error(actual, predicted)),
        "mean_absolute_error": MetricValue.computed(mean_absolute_error(actual, predicted)),
        "nasa_score": MetricValue.computed(nasa_asymmetric_score(unit_actual, unit_predicted)),
    }


def score_named_errors(
    *,
    actual: Sequence[float],
    predicted: Sequence[float],
) -> dict[str, MetricValue]:
    """Score one paired sample as root-mean-square error, MAE, and NASA score.

    Args:
        actual: Observed remaining life.
        predicted: Predicted remaining life in the same order.

    Returns:
        Three computed metrics. The NASA score is included and is not a gate.
    """
    return {
        "root_mean_square_error": MetricValue.computed(root_mean_square_error(actual, predicted)),
        "mean_absolute_error": MetricValue.computed(mean_absolute_error(actual, predicted)),
        "nasa_score": MetricValue.computed(nasa_asymmetric_score(actual, predicted)),
    }


def choose_headline(
    *,
    constant_validation_rmse: MetricValue,
    tree_validation_rmse: MetricValue,
) -> BaselineName:
    """Choose the model from validation root-mean-square error only.

    The returned model is the one whose test scores are the headline
    evaluation. Mean absolute error is reported beside the selection score.
    The NASA score is not an argument: a better NASA score cannot win, and
    a worse one cannot lose. The test split is not an argument.

    Args:
        constant_validation_rmse: Constant model on the validation split.
        tree_validation_rmse: Tree model on the validation split.

    Returns:
        The tree when its validation root-mean-square error is strictly
        lower. Otherwise the constant, including ties and any split that
        was not computed.
    """
    constant_value = _computed_number(constant_validation_rmse)
    tree_value = _computed_number(tree_validation_rmse)
    if constant_value is None or tree_value is None:
        return BaselineName.CONSTANT
    if tree_value < constant_value:
        return BaselineName.HIST_GRADIENT_BOOSTING
    return BaselineName.CONSTANT


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
        Root-mean-square error, mean absolute error, and the NASA score.

    Raises:
        ContractError: The split name is unknown, or the identifiers differ.
    """
    if split_name not in _SPLIT_NAMES:
        raise ContractError(f"Unknown split {split_name!r}. Use train, validation, or test.")
    if set(predicted) != set(actual):
        raise ContractError(f"Predicted and actual identifiers differ on {split_name}.")
    keys = tuple(sorted(actual))
    values = score_named_errors(
        actual=tuple(actual[key] for key in keys),
        predicted=tuple(predicted[key] for key in keys),
    )
    return SplitMetrics(values=values)


def _pairs(actual: Sequence[float], predicted: Sequence[float]) -> tuple[tuple[float, float], ...]:
    """Pair actual and predicted values after checking the contract.

    Args:
        actual: Observed values.
        predicted: Predicted values.

    Returns:
        Pairs in the given order.

    Raises:
        ContractError: The sequences differ in length or are empty.
    """
    if len(actual) != len(predicted):
        raise ContractError("Actual and predicted remaining life must have the same length.")
    if not actual:
        raise ContractError("A remaining-life score needs at least one row.")
    return tuple(zip(actual, predicted, strict=True))


def _computed_number(metric: MetricValue) -> float | None:
    """Return the number on a computed metric.

    Args:
        metric: One report metric.

    Returns:
        The value when the status is ``COMPUTED``, otherwise None.
    """
    if metric.status is not MetricComputationStatus.COMPUTED:
        return None
    return metric.value
