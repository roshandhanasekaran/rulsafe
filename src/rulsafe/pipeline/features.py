"""Causal feature values.

The default gap policy leaves missing values missing. Bounded forward fill
is allowed. Linear interpolation is not. A feature at time ``t`` is computed
only from records whose available time is at or before ``t``.
"""

from collections.abc import Mapping, Sequence

from rulsafe.contract import GapPolicy
from rulsafe.exceptions import not_implemented


def build_causal_features(
    *,
    rows: Sequence[Mapping[str, object]],
    prediction_time: int | float,
    gap_policy: GapPolicy,
    maximum_gap: int | None,
    feature_columns: Sequence[str],
) -> Mapping[str, object]:
    """Build feature values that were knowable at ``prediction_time``.

    Args:
        rows: Candidate signal rows for one episode.
        prediction_time: Time ``t`` at which the features must be computable.
        gap_policy: ``none`` or bounded forward fill.
        maximum_gap: Largest forward fill. Required when the policy is forward fill.
        feature_columns: Explicit allowlist. Identifiers are not features.

    Returns:
        Feature name to value for this prediction time.

    Raises:
        NotImplementedError: Feature building is not implemented yet.
    """
    raise not_implemented(
        "build_causal_features",
        rows,
        prediction_time,
        gap_policy,
        maximum_gap,
        feature_columns,
    )
