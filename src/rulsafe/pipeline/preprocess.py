"""Train-only preprocessing and the membership record that proves it.

Clip bounds and scalers are fit on the training rows only. Fitting them on
validation or test is confirmed leakage. A column whose spread is only
float dust is not divided by that dust: it is centered and then left on a
scale of 1, so a near-constant column becomes about zero on every
interpreter instead of exploding on one of them.
"""

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rulsafe.config import ScalerName
from rulsafe.exceptions import ContractError

# Spread at or below this fraction of the column's magnitude is float dust.
# CPython and NumPy builds do not agree on those residuals. Treating them as
# a real scale makes the same FD001 matrix train a different tree.
RELATIVE_SCALE_TOLERANCE = 1e-8


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


@dataclass(frozen=True)
class FittedPreprocessor:
    """Clip bounds and a scaler fit on the training split.

    Attributes:
        feature_names: Columns the transform emits.
        clip_low: Low clip bound by feature, fit on train.
        clip_high: High clip bound by feature, fit on train.
        center: Value subtracted after clipping. Zero when the scaler is ``none``.
        scale: Value divided by after centering. Never zero.
        scaler: ``standard``, ``minmax``, or ``none``.
        membership: Train-split membership record.
        fitted_asset_ids: Asset id of every row passed into the fit, in that order.
    """

    feature_names: tuple[str, ...]
    clip_low: Mapping[str, float]
    clip_high: Mapping[str, float]
    center: Mapping[str, float]
    scale: Mapping[str, float]
    scaler: str
    membership: TransformerMembership
    fitted_asset_ids: tuple[str, ...] = ()

    def transform(self, features: Mapping[str, float | None]) -> dict[str, float | None]:
        """Clip and scale one row with the training bounds.

        Args:
            features: Causal features. Missing values stay missing.

        Returns:
            The transformed row. A missing input stays None.
        """
        transformed: dict[str, float | None] = {}
        for name in self.feature_names:
            raw = features.get(name)
            if raw is None:
                transformed[name] = None
                continue
            clipped = min(max(float(raw), self.clip_low[name]), self.clip_high[name])
            transformed[name] = (clipped - self.center[name]) / self.scale[name]
        return transformed


def fit_preprocessors(
    rows: Sequence[Mapping[str, float | None]],
    *,
    asset_ids: Sequence[str],
    feature_names: Sequence[str],
    clip_percentiles: tuple[float, float],
    scaler: ScalerName,
) -> FittedPreprocessor:
    """Fit clip bounds and a scaler on training rows.

    Percentiles use linear interpolation on the sorted finite training
    values. Means and variances use ``math.fsum``. The standard scaler then
    subtracts the mean of the clipped values and divides by their population
    standard deviation. Min-max divides by the clipped range. A deviation
    that is zero, or only float dust relative to the column magnitude, is
    replaced by 1 so the column is centered and not amplified.

    Args:
        rows: Training feature rows. Validation and test rows are not accepted.
        asset_ids: Asset id of each training row, in the same order.
        feature_names: Columns to fit.
        clip_percentiles: Low and high percentiles, in percent.
        scaler: ``standard``, ``minmax``, or ``none``.

    Returns:
        A preprocessor whose membership names the train split.

    Raises:
        ContractError: There are no training rows, or the asset ids do not align.
    """
    if not rows:
        raise ContractError("The preprocessor needs at least one training row.")
    if len(rows) != len(asset_ids):
        raise ContractError("Training feature rows and asset ids must have the same length.")
    names = tuple(feature_names)
    low_quantile, high_quantile = clip_percentiles
    clip_low: dict[str, float] = {}
    clip_high: dict[str, float] = {}
    center: dict[str, float] = {}
    scale: dict[str, float] = {}
    for name in names:
        values: list[float] = []
        for row in rows:
            cell = row.get(name)
            if isinstance(cell, (int, float)) and not isinstance(cell, bool):
                values.append(float(cell))
        if not values:
            clip_low[name] = 0.0
            clip_high[name] = 0.0
            center[name] = 0.0
            scale[name] = 1.0
            continue
        low = _percentile(values, low_quantile)
        high = _percentile(values, high_quantile)
        clipped = [min(max(value, low), high) for value in values]
        clip_low[name] = low
        clip_high[name] = high
        fitted_center, fitted_scale = _center_and_scale(clipped, scaler)
        center[name] = fitted_center
        scale[name] = fitted_scale
    identity = "\n".join(sorted(set(asset_ids))) + f"\n{len(rows)}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    membership = TransformerMembership(
        transformer_name=f"clip_percentiles+{scaler.value}",
        split_name="train",
        fitted_row_count=len(rows),
        membership_hash=digest,
        statistics={"feature_count": float(len(names))},
    )
    return FittedPreprocessor(
        feature_names=names,
        clip_low=clip_low,
        clip_high=clip_high,
        center=center,
        scale=scale,
        scaler=scaler.value,
        membership=membership,
        fitted_asset_ids=tuple(asset_ids),
    )


def _center_and_scale(clipped: Sequence[float], scaler: ScalerName) -> tuple[float, float]:
    """Return the center and the non-zero scale for one clipped column.

    Args:
        clipped: Training values after the percentile clip.
        scaler: Requested scaler.

    Returns:
        Center and scale. ``none`` returns ``0`` and ``1``.
    """
    if scaler is ScalerName.NONE:
        return 0.0, 1.0
    if scaler is ScalerName.MINMAX:
        low = min(clipped)
        high = max(clipped)
        span = high - low
        magnitude = max(1.0, abs(low), abs(high))
        return low, _usable_scale(span, magnitude)
    mean, deviation = _mean_and_deviation(clipped)
    magnitude = max(1.0, abs(mean), max(abs(value) for value in clipped))
    return mean, _usable_scale(deviation, magnitude)


def _mean_and_deviation(values: Sequence[float]) -> tuple[float, float]:
    """Return the mean and population standard deviation.

    Args:
        values: Finite sample. It is not empty.

    Returns:
        Mean and population standard deviation. A constant sample has
        deviation 0.
    """
    count = float(len(values))
    mean = math.fsum(values) / count
    variance = math.fsum((value - mean) ** 2 for value in values) / count
    if variance <= 0.0:
        return mean, 0.0
    return mean, math.sqrt(variance)


def _usable_scale(deviation: float, magnitude: float) -> float:
    """Return a divisor that ignores float dust.

    Args:
        deviation: Spread of the column. Zero means the column is constant.
        magnitude: Size of the column, at least 1.

    Returns:
        ``deviation`` when it is large enough to be a real scale, otherwise 1.
    """
    if not math.isfinite(deviation):
        return 1.0
    if deviation <= RELATIVE_SCALE_TOLERANCE * magnitude:
        return 1.0
    return deviation


def _percentile(values: Sequence[float], quantile: float) -> float:
    """Return a linearly interpolated percentile.

    Args:
        values: Finite sample.
        quantile: Percentile in the range 0 to 100.

    Returns:
        The percentile. A one-value sample returns that value.
    """
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (quantile / 100.0)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight
