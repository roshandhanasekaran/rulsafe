"""Train-only preprocessing and the membership record that proves it.

Scalers, clip bounds, and imputers fit on the training split only. Fitting
on validation or test is confirmed leakage.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from rulsafe.exceptions import not_implemented


@dataclass(frozen=True)
class TransformerMembership:
    """Proof that a transformer was fit on the training split.

    Attributes:
        transformer_name: Scaler, clip, or imputer name.
        split_name: Must be ``train``.
        fitted_row_count: Number of training rows used in the fit.
        membership_hash: Hash of the fitted entity or row identifiers.
        statistics: Numeric state needed to audit a later transform.
    """

    transformer_name: str
    split_name: str
    fitted_row_count: int
    membership_hash: str
    statistics: Mapping[str, float]

    def __post_init__(self) -> None:
        """Reject a membership record that was not fit on train."""
        if self.split_name != "train":
            raise ValueError("Transformers fit on the train split only.")
        if self.fitted_row_count < 0:
            raise ValueError("fitted_row_count must be zero or greater.")
        if not self.transformer_name.strip():
            raise ValueError("transformer_name must not be empty.")
        if not self.membership_hash.strip():
            raise ValueError("membership_hash must not be empty.")


def fit_preprocessors(
    *,
    training_row_count: int,
    training_membership_hash: str,
) -> tuple[TransformerMembership, ...]:
    """Fit clip bounds and scalers on the training split and record membership.

    Args:
        training_row_count: Number of rows in the training split.
        training_membership_hash: Hash of the training entity identifiers.

    Returns:
        One membership record per transformer.

    Raises:
        NotImplementedError: Fitting is not implemented yet.
    """
    raise not_implemented(
        "fit_preprocessors",
        training_row_count,
        training_membership_hash,
    )
