"""v0.1 baselines: a training constant and one histogram gradient boosting model.

Persistence is rejected by :func:`rulsafe.models.forbid_persistence.reject_persistence_baseline`.
Age and logistic regression are not v0.1 baselines. Both models that are
fit here use the training split only. Early stopping, when the validation
split has scored rows, uses that split and does not hold out training rows.
The headline model is chosen on validation root-mean-square error. The final
test is scored once and is not an argument of either fit function.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rulsafe.config import BaselineName
from rulsafe.exceptions import ContractError

# Fixed tree shape. Only the iteration count is chosen, and only on validation.
FIXED_ITERATION_CAP = 40
_LEARNING_RATE = 0.1
_MAX_DEPTH = 3
_MAX_LEAF_NODES = 15
_MIN_SAMPLES_LEAF = 1
_L2_REGULARIZATION = 0.0
_EARLY_STOPPING_PATIENCE = 5
_EARLY_STOPPING_TOLERANCE = 1e-7


@dataclass(frozen=True)
class FittedBaseline:
    """A baseline fit on the training split.

    Attributes:
        name: ``constant`` or ``hist_gradient_boosting``.
        training_row_count: Rows used to fit the model. Validation rows are not included.
        constant_value: Training mean for the constant baseline. None for other models.
        iteration_count: Boosting iterations kept after early stopping, or the
            fixed cap when validation had no scored rows.
        random_state: Seed passed to the tree. None for the constant model.
        early_stopping_split: ``validation`` when that split chose the iteration
            count. None when a fixed cap was used.
        feature_names: Column order of the tree. Empty for the constant model.
        estimator: Fitted histogram gradient boosting model. Not part of equality.
    """

    name: BaselineName
    training_row_count: int
    constant_value: float | None = None
    iteration_count: int | None = None
    random_state: int | None = None
    early_stopping_split: str | None = None
    feature_names: tuple[str, ...] = ()
    estimator: Any = field(default=None, compare=False, repr=False)

    def predict(self, features: Sequence[Mapping[str, float | None]]) -> tuple[float, ...]:
        """Predict remaining life for rows that were not used to fit this model.

        Args:
            features: Causal features in any key order. The tree uses the
                training column order.

        Returns:
            One prediction per row.

        Raises:
            ContractError: The model has no fitted value.
        """
        if self.name is BaselineName.CONSTANT:
            if self.constant_value is None:
                raise ContractError("The constant baseline has no training value.")
            return tuple(self.constant_value for _ in features)
        if self.estimator is None:
            raise ContractError("The tree baseline is not fitted.")
        matrix = _feature_matrix(features, self.feature_names)
        predicted = self.estimator.predict(matrix)
        return tuple(float(value) for value in predicted)

    def __post_init__(self) -> None:
        """Reject a fit record that did not see a non-negative training count."""
        if self.training_row_count < 0:
            raise ValueError("training_row_count must be zero or greater.")


def fit_constant_baseline(*, training_targets: Sequence[float]) -> FittedBaseline:
    """Fit the constant baseline: the training mean of the remaining-life target.

    Args:
        training_targets: Completed-trajectory targets from the training split.

    Returns:
        A constant model whose value is the training mean. Held-out targets
        are not an argument, so they cannot move this value.

    Raises:
        ContractError: There is no training target.
    """
    if not training_targets:
        raise ContractError("The constant baseline needs at least one training target.")
    mean_value = sum(training_targets) / len(training_targets)
    return FittedBaseline(
        name=BaselineName.CONSTANT,
        training_row_count=len(training_targets),
        constant_value=mean_value,
    )


def fit_histogram_gradient_boosting(
    *,
    training_features: Sequence[Mapping[str, float | None]],
    training_targets: Sequence[float],
    validation_features: Sequence[Mapping[str, float | None]] | None = None,
    validation_targets: Sequence[float] | None = None,
    random_state: int,
) -> FittedBaseline:
    """Fit one histogram gradient boosting model on training rows only.

    When validation rows are present, scikit-learn early stopping uses that
    split. ``validation_fraction`` is left unset, so no training row is held
    out at random. The test split is not an argument.

    Args:
        training_features: Allowlisted causal features from the training split.
        training_targets: Remaining-life targets from the training split.
        validation_features: Validation features used only to choose the
            iteration count. Omit them when that split has no scored rows.
        validation_targets: Validation targets paired with ``validation_features``.
        random_state: Project seed. The same seed and rows repeat the fit.

    Returns:
        The fitted tree. ``training_row_count`` is the training length only.

    Raises:
        ContractError: The training rows are missing, or a pair of sequences
            has different lengths.
    """
    _require_aligned("Training", training_features, training_targets)
    if not training_features:
        raise ContractError("The tree baseline needs at least one training row.")
    feature_names = _feature_names(training_features)
    training_matrix = _feature_matrix(training_features, feature_names)
    use_validation = validation_features is not None or validation_targets is not None
    validation_matrix: list[list[float]] | None = None
    if use_validation:
        if validation_features is None or validation_targets is None:
            raise ContractError("Early stopping needs both validation features and targets.")
        _require_aligned("Validation", validation_features, validation_targets)
        if not validation_features:
            raise ContractError("Early stopping needs at least one validation row.")
        validation_matrix = _feature_matrix(validation_features, feature_names)
    estimator, iteration_count = _fit_hist_gradient_boosting(
        training_matrix=training_matrix,
        training_targets=training_targets,
        validation_matrix=validation_matrix,
        validation_targets=validation_targets,
        random_state=random_state,
    )
    return FittedBaseline(
        name=BaselineName.HIST_GRADIENT_BOOSTING,
        training_row_count=len(training_targets),
        iteration_count=iteration_count,
        random_state=random_state,
        early_stopping_split="validation" if validation_matrix is not None else None,
        feature_names=feature_names,
        estimator=estimator,
    )


def _require_aligned(
    label: str,
    features: Sequence[Mapping[str, float | None]],
    targets: Sequence[float],
) -> None:
    """Reject a feature matrix whose row count differs from its targets.

    Args:
        label: ``Training`` or ``Validation``, used in the error.
        features: Feature rows.
        targets: Targets for those rows.

    Raises:
        ContractError: The lengths differ.
    """
    if len(features) != len(targets):
        raise ContractError(f"{label} features and targets must have the same length.")


def _feature_names(rows: Sequence[Mapping[str, float | None]]) -> tuple[str, ...]:
    """Return a stable column order from the training rows.

    Args:
        rows: Training feature mappings.

    Returns:
        Sorted feature names.

    Raises:
        ContractError: No feature column is present.
    """
    names: set[str] = set()
    for row in rows:
        names.update(row)
    if not names:
        raise ContractError("The tree baseline needs at least one feature column.")
    return tuple(sorted(names))


def _feature_matrix(
    rows: Sequence[Mapping[str, float | None]],
    names: Sequence[str],
) -> list[list[float]]:
    """Build a numeric matrix in the training column order.

    Args:
        rows: Feature mappings.
        names: Column order fixed at fit time.

    Returns:
        One list of floats per row. Missing values are NaN, which the tree
        model accepts without imputation.
    """
    return [[_feature_cell(row.get(name)) for name in names] for row in rows]


def _feature_cell(value: object) -> float:
    """Convert one feature cell to a float.

    Args:
        value: A number, or None when the causal feature is missing.

    Returns:
        The float value, or NaN when the cell is missing.

    Raises:
        ContractError: The cell is not numeric.
    """
    if value is None:
        return math.nan
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"Feature values must be numeric, got {value!r}.")
    number = float(value)
    if not math.isfinite(number):
        raise ContractError("Feature values must be finite.")
    return number


def _fit_hist_gradient_boosting(
    *,
    training_matrix: list[list[float]],
    training_targets: Sequence[float],
    validation_matrix: list[list[float]] | None,
    validation_targets: Sequence[float] | None,
    random_state: int,
) -> tuple[Any, int]:
    """Fit scikit-learn's histogram gradient boosting regressor.

    The import stays inside this function so importing the package does not
    import scikit-learn.

    Args:
        training_matrix: Training features only.
        training_targets: Training targets only.
        validation_matrix: Validation features, or None to skip early stopping.
        validation_targets: Validation targets paired with the matrix.
        random_state: Project seed.

    Returns:
        The fitted estimator and the iteration count it kept.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor  # type: ignore[import-untyped]

    early_stopping = validation_matrix is not None
    model = HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=_LEARNING_RATE,
        max_iter=FIXED_ITERATION_CAP,
        max_depth=_MAX_DEPTH,
        max_leaf_nodes=_MAX_LEAF_NODES,
        min_samples_leaf=_MIN_SAMPLES_LEAF,
        l2_regularization=_L2_REGULARIZATION,
        early_stopping=early_stopping,
        validation_fraction=None,
        n_iter_no_change=_EARLY_STOPPING_PATIENCE,
        tol=_EARLY_STOPPING_TOLERANCE,
        random_state=random_state,
    )
    if validation_matrix is None:
        model.fit(training_matrix, list(training_targets))
    else:
        model.fit(
            training_matrix,
            list(training_targets),
            X_val=validation_matrix,
            y_val=list(validation_targets or ()),
        )
    return model, int(model.n_iter_)
