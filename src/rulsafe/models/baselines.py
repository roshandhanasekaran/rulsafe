"""v0.1 baselines: a training constant and one histogram gradient boosting model.

Persistence is rejected by :func:`rulsafe.models.forbid_persistence.reject_persistence_baseline`.
Age and logistic regression are not v0.1 baselines. Both models that are
fit here use the training split only. The headline model is chosen on
validation, then the final test is scored once.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rulsafe.config import BaselineName
from rulsafe.exceptions import not_implemented


@dataclass(frozen=True)
class FittedBaseline:
    """A baseline fit on the training split.

    Attributes:
        name: ``constant`` or ``hist_gradient_boosting``.
        training_row_count: Rows used to fit the model.
    """

    name: BaselineName
    training_row_count: int

    def __post_init__(self) -> None:
        """Reject a fit record that did not see a non-negative training count."""
        if self.training_row_count < 0:
            raise ValueError("training_row_count must be zero or greater.")


def fit_constant_baseline(*, training_targets: Sequence[float]) -> FittedBaseline:
    """Fit the constant baseline: the training mean of the remaining-life target.

    Args:
        training_targets: Completed-trajectory targets from the training split.

    Returns:
        A constant model. Validation chooses any threshold or display cutoff.

    Raises:
        NotImplementedError: Fitting is not implemented yet.
    """
    raise not_implemented("fit_constant_baseline", training_targets)


def fit_histogram_gradient_boosting(
    *,
    training_features: Sequence[Mapping[str, float]],
    training_targets: Sequence[float],
) -> FittedBaseline:
    """Fit one histogram gradient boosting model on training rows.

    Args:
        training_features: Allowlisted causal features from the training split.
        training_targets: Remaining-life targets from the training split.

    Returns:
        The fitted tree model.

    Raises:
        NotImplementedError: Fitting is not implemented yet.
    """
    raise not_implemented(
        "fit_histogram_gradient_boosting",
        training_features,
        training_targets,
    )
