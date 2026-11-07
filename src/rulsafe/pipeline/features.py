"""Causal feature values.

The default gap policy leaves missing values missing. Bounded forward fill
is allowed. Linear interpolation is not. A feature at time ``t`` is computed
only from records whose event time and available time are at or before ``t``.
"""

from collections.abc import Mapping, Sequence

from rulsafe.contract import GapPolicy
from rulsafe.exceptions import ConfigurationError


def build_causal_features(
    *,
    rows: Sequence[Mapping[str, object]],
    prediction_time: int | float,
    gap_policy: GapPolicy,
    maximum_gap: int | None,
    feature_columns: Sequence[str],
) -> Mapping[str, float | None]:
    """Build feature values that were knowable at ``prediction_time``.

    Rows must already use ``event_time`` and ``available_at`` keys. A later
    row in ``rows`` does not change the value at an earlier prediction time.

    Args:
        rows: Candidate signal rows for one episode.
        prediction_time: Time ``t`` at which the features must be computable.
        gap_policy: ``none`` or bounded forward fill.
        maximum_gap: Largest forward fill. Required when the policy is forward fill.
        feature_columns: Explicit allowlist. Identifiers are not features.

    Returns:
        Feature name to value for this prediction time. Missing values are None.

    Raises:
        ConfigurationError: Forward fill was requested without ``maximum_gap``.
    """
    if gap_policy is GapPolicy.FORWARD_FILL and maximum_gap is None:
        raise ConfigurationError("max_gap is required when gap_policy is ffill.")
    values: dict[str, float | None] = {}
    for column_name in feature_columns:
        values[column_name] = _causal_column_value(
            rows,
            prediction_time=float(prediction_time),
            column_name=column_name,
            gap_policy=gap_policy,
            maximum_gap=maximum_gap,
        )
    return values


def _causal_column_value(
    rows: Sequence[Mapping[str, object]],
    *,
    prediction_time: float,
    column_name: str,
    gap_policy: GapPolicy,
    maximum_gap: int | None,
) -> float | None:
    """Return the latest causal value of one column.

    Args:
        rows: Candidate rows.
        prediction_time: Time ``t``.
        column_name: Feature column.
        gap_policy: ``none`` or bounded forward fill.
        maximum_gap: Largest age of a filled value.

    Returns:
        The value, or None when no causal row has one.
    """
    chosen: tuple[float, float, float] | None = None
    for row in rows:
        event_time = _required_time(row, "event_time")
        available_at = _required_time(row, "available_at")
        if event_time > prediction_time or available_at > prediction_time:
            continue
        too_old = (
            gap_policy is GapPolicy.FORWARD_FILL
            and maximum_gap is not None
            and prediction_time - event_time > maximum_gap
        )
        if too_old:
            continue
        numeric = _optional_float(row.get(column_name))
        if numeric is None:
            continue
        candidate = (event_time, available_at, numeric)
        if chosen is None or candidate[:2] >= chosen[:2]:
            chosen = candidate
    if chosen is None:
        return None
    return chosen[2]


def _required_time(row: Mapping[str, object], key: str) -> float:
    """Read a required time field.

    Args:
        row: Signal row.
        key: ``event_time`` or ``available_at``.

    Returns:
        The time as a float.

    Raises:
        ConfigurationError: The field is missing or not numeric.
    """
    if key not in row:
        raise ConfigurationError(f"Signal row is missing {key}.")
    numeric = _optional_float(row[key])
    if numeric is None:
        raise ConfigurationError(f"Signal row has a blank {key}.")
    return numeric


def _optional_float(value: object) -> float | None:
    """Convert a cell to a float.

    Args:
        value: Cell value.

    Returns:
        None when the cell is empty.

    Raises:
        ConfigurationError: The cell is not numeric.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ConfigurationError(f"Expected a number, got {value!r}.")
    try:
        return float(value)
    except ValueError as error:
        raise ConfigurationError(f"Expected a number, got {value!r}.") from error
