"""Histogram gradient boosting stays on the training split and repeats."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from rulsafe.exceptions import ContractError
from rulsafe.models.baselines import FIXED_ITERATION_CAP, fit_histogram_gradient_boosting


def _rows(values: tuple[float, ...]) -> tuple[dict[str, float], ...]:
    return tuple({"signal": value} for value in values)


def test_tree_early_stops_on_validation_and_ignores_a_later_probe() -> None:
    """Validation can change the iteration count. A probe row is only predicted."""
    training_x = _rows(tuple(float(index) for index in range(8)))
    training_y = tuple(value * 2.0 + 1.0 for value in range(8))
    validation_x = _rows((0.5, 2.5, 4.5, 6.5))
    validation_y = tuple(value * 2.0 + 1.0 for value in (0.5, 2.5, 4.5, 6.5))
    first = fit_histogram_gradient_boosting(
        training_features=training_x,
        training_targets=training_y,
        validation_features=validation_x,
        validation_targets=validation_y,
        random_state=7,
    )
    second = fit_histogram_gradient_boosting(
        training_features=training_x,
        training_targets=training_y,
        validation_features=validation_x,
        validation_targets=validation_y,
        random_state=7,
    )
    probe = ({"signal": 1.5}, {"signal": 9.0})
    assert first.training_row_count == len(training_y)
    assert first.early_stopping_split == "validation"
    assert first.iteration_count is not None
    assert first.iteration_count < FIXED_ITERATION_CAP
    assert first.iteration_count == second.iteration_count
    assert first.predict(probe) == second.predict(probe)
    again = first.predict(probe)
    assert first.predict(probe) == again
    assert len(first.predict(({},))) == 1

    noisy = fit_histogram_gradient_boosting(
        training_features=training_x,
        training_targets=training_y,
        validation_features=validation_x,
        validation_targets=(0.0, 0.0, 0.0, 0.0),
        random_state=7,
    )
    assert noisy.training_row_count == len(training_y)
    assert noisy.iteration_count != first.iteration_count

    fixed = fit_histogram_gradient_boosting(
        training_features=training_x,
        training_targets=training_y,
        random_state=7,
    )
    assert fixed.early_stopping_split is None
    assert fixed.iteration_count == FIXED_ITERATION_CAP
    assert fixed.training_row_count == len(training_y)


def test_unfitted_baselines_and_bad_feature_cells_are_rejected() -> None:
    """Predict and fit refuse a model or a cell that cannot be scored."""
    from rulsafe.config import BaselineName
    from rulsafe.models.baselines import FittedBaseline

    constant = FittedBaseline(name=BaselineName.CONSTANT, training_row_count=1)
    with pytest.raises(ContractError, match="training value"):
        constant.predict(({"signal": 1.0},))
    bare_tree = FittedBaseline(name=BaselineName.HIST_GRADIENT_BOOSTING, training_row_count=1)
    with pytest.raises(ContractError, match="not fitted"):
        bare_tree.predict(({"signal": 1.0},))
    with pytest.raises(ContractError, match="both validation"):
        fit_histogram_gradient_boosting(
            training_features=({"signal": 1.0},),
            training_targets=(1.0,),
            validation_features=({"signal": 1.0},),
            validation_targets=None,
            random_state=1,
        )
    with pytest.raises(ContractError, match="feature column"):
        fit_histogram_gradient_boosting(
            training_features=({},),
            training_targets=(1.0,),
            random_state=1,
        )
    with pytest.raises(ContractError, match="numeric"):
        fit_histogram_gradient_boosting(
            training_features=({"signal": "hot"},),  # type: ignore[dict-item]
            training_targets=(1.0,),
            random_state=1,
        )
    with pytest.raises(ContractError, match="numeric"):
        fit_histogram_gradient_boosting(
            training_features=({"signal": True},),
            training_targets=(1.0,),
            random_state=1,
        )
    with pytest.raises(ContractError, match="Validation"):
        fit_histogram_gradient_boosting(
            training_features=({"signal": 1.0},),
            training_targets=(1.0,),
            validation_features=({"signal": 1.0}, {"signal": 2.0}),
            validation_targets=(1.0,),
            random_state=1,
        )
    with pytest.raises(ContractError, match="finite"):
        fit_histogram_gradient_boosting(
            training_features=({"signal": float("inf")},),
            training_targets=(1.0,),
            random_state=1,
        )
    with pytest.raises(ContractError, match="at least one validation"):
        fit_histogram_gradient_boosting(
            training_features=({"signal": 1.0},),
            training_targets=(1.0,),
            validation_features=(),
            validation_targets=(),
            random_state=1,
        )


def test_tree_rejects_empty_or_unaligned_training_rows() -> None:
    """A fit with no training target, or a ragged pair, does not silently drop rows."""
    with pytest.raises(ContractError, match="training row"):
        fit_histogram_gradient_boosting(
            training_features=(),
            training_targets=(),
            random_state=1,
        )
    with pytest.raises(ContractError, match="same length"):
        fit_histogram_gradient_boosting(
            training_features=({"signal": 1.0},),
            training_targets=(1.0, 2.0),
            random_state=1,
        )


@given(
    seed=st.integers(min_value=0, max_value=10_000),
    slope=st.floats(min_value=-3, max_value=3, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=6, deadline=None)
def test_tree_fit_is_deterministic(seed: int, slope: float) -> None:
    """The same seed and rows produce the same iteration count and predictions."""
    training_x = _rows(tuple(float(index) for index in range(6)))
    training_y = tuple(slope * index for index in range(6))
    validation_x = _rows((0.25, 1.25, 2.25))
    validation_y = tuple(slope * value for value in (0.25, 1.25, 2.25))
    first = fit_histogram_gradient_boosting(
        training_features=training_x,
        training_targets=training_y,
        validation_features=validation_x,
        validation_targets=validation_y,
        random_state=seed,
    )
    second = fit_histogram_gradient_boosting(
        training_features=training_x,
        training_targets=training_y,
        validation_features=validation_x,
        validation_targets=validation_y,
        random_state=seed,
    )
    probe = ({"signal": 1.5},)
    assert first.iteration_count == second.iteration_count
    assert first.predict(probe) == second.predict(probe)
    assert first.training_row_count == 6
