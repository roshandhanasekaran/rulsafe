"""Property tests for remaining-life scores.

The NASA score is reported. It is not a reason to accept or reject a model.
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from rulsafe.config import BaselineName
from rulsafe.eval.cmapss_last_obs import score_last_observation
from rulsafe.eval.metrics import (
    choose_headline,
    mean_absolute_error,
    nasa_asymmetric_score,
    root_mean_square_error,
    score_remaining_life,
)
from rulsafe.exceptions import ContractError
from rulsafe.report.json import MetricValue

_finite = st.floats(min_value=-40, max_value=40, allow_nan=False, allow_infinity=False)


@given(
    pairs=st.lists(st.tuples(_finite, _finite), min_size=1, max_size=12),
    data=st.data(),
)
@settings(max_examples=40)
def test_scores_are_nonnegative_order_invariant_and_rmse_bounds_mae(
    pairs: list[tuple[float, float]],
    data: st.DataObject,
) -> None:
    """RMSE, MAE, and the NASA score depend on the pairs, not their order."""
    actual = [truth for truth, _ in pairs]
    predicted = [guess for _, guess in pairs]
    permutation = data.draw(st.permutations(list(range(len(pairs)))))
    shuffled_actual = [actual[index] for index in permutation]
    shuffled_predicted = [predicted[index] for index in permutation]
    rmse = root_mean_square_error(actual, predicted)
    mae = mean_absolute_error(actual, predicted)
    nasa = nasa_asymmetric_score(actual, predicted)
    assert rmse >= 0
    assert mae >= 0
    assert nasa >= 0
    assert math.isfinite(rmse)
    assert math.isfinite(mae)
    assert math.isfinite(nasa)
    assert rmse + 1e-9 >= mae
    assert root_mean_square_error(shuffled_actual, shuffled_predicted) == pytest.approx(rmse)
    assert mean_absolute_error(shuffled_actual, shuffled_predicted) == pytest.approx(mae)
    assert nasa_asymmetric_score(shuffled_actual, shuffled_predicted) == pytest.approx(nasa)


def test_perfect_predictions_score_zero_and_late_costs_more_than_early() -> None:
    """A perfect vector is zero. A late error costs more than the matching early error."""
    assert root_mean_square_error((1.0, 2.0), (1.0, 2.0)) == 0.0
    assert mean_absolute_error((1.0, 2.0), (1.0, 2.0)) == 0.0
    assert nasa_asymmetric_score((0.0,), (0.0,)) == 0.0
    late = nasa_asymmetric_score((0.0,), (10.0,))
    early = nasa_asymmetric_score((0.0,), (-10.0,))
    assert late > early


def test_headline_uses_validation_rmse_and_not_the_nasa_score() -> None:
    """A lower validation RMSE wins even when that model would have a worse NASA score."""
    chosen = choose_headline(
        constant_validation_rmse=MetricValue.computed(5.0),
        tree_validation_rmse=MetricValue.computed(1.0),
    )
    assert chosen is BaselineName.HIST_GRADIENT_BOOSTING
    tied = choose_headline(
        constant_validation_rmse=MetricValue.computed(1.0),
        tree_validation_rmse=MetricValue.computed(1.0),
    )
    assert tied is BaselineName.CONSTANT
    missing = choose_headline(
        constant_validation_rmse=MetricValue.computed(1.0),
        tree_validation_rmse=MetricValue.not_computed(),
    )
    assert missing is BaselineName.CONSTANT


def test_score_remaining_life_and_last_observation_reject_bad_pairs() -> None:
    """Identifiers and lengths are part of the scoring contract."""
    scored = score_remaining_life(
        predicted={"engine_b": 2.0, "engine_a": 1.0},
        actual={"engine_a": 1.0, "engine_b": 4.0},
        split_name="test",
    )
    assert scored.values["root_mean_square_error"].status.value == "COMPUTED"
    assert scored.values["nasa_score"].value is not None
    with pytest.raises(ContractError, match="identifiers"):
        score_remaining_life(predicted={"a": 1.0}, actual={"b": 1.0}, split_name="test")
    with pytest.raises(ContractError, match="Unknown split"):
        score_remaining_life(predicted={"a": 1.0}, actual={"a": 1.0}, split_name="holdout")
    last = score_last_observation(
        predicted_remaining_cycles=(10.0, 20.0),
        true_remaining_cycles=(10.0, 30.0),
    )
    assert set(last) == {"root_mean_square_error", "mean_absolute_error", "nasa_score"}
    with pytest.raises(ContractError, match="same length"):
        score_last_observation(predicted_remaining_cycles=(1.0,), true_remaining_cycles=(1.0, 2.0))
    with pytest.raises(ContractError, match="at least one"):
        root_mean_square_error((), ())
    with pytest.raises(ContractError, match="same length"):
        mean_absolute_error((1.0,), (1.0, 2.0))
    with pytest.raises(ContractError, match="at least one engine"):
        score_last_observation(predicted_remaining_cycles=(), true_remaining_cycles=())
