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


def lookback_feature_names(feature_columns: Sequence[str]) -> tuple[str, ...]:
    """Return last, mean, and slope names for each allowlisted column.

    Args:
        feature_columns: Explicit allowlist. Identifiers are not included.

    Returns:
        ``column``, ``column_mean``, and ``column_slope`` for each column.

    Raises:
        ConfigurationError: The allowlist is empty or two names collide.
    """
    names: list[str] = []
    seen: set[str] = set()
    for column_name in feature_columns:
        for suffix in ("", "_mean", "_slope"):
            feature_name = f"{column_name}{suffix}"
            if feature_name in seen:
                raise ConfigurationError(
                    f"Lookback feature name {feature_name!r} collides with another feature."
                )
            seen.add(feature_name)
            names.append(feature_name)
    if not names:
        raise ConfigurationError("Lookback features need at least one column.")
    return tuple(names)


def features_from_windows(
    windows: Sequence[Mapping[str, object]],
    feature_columns: Sequence[str],
) -> list[dict[str, float | None]]:
    """Turn causal windows into last, mean, and slope features.

    The window is the only input. A row that was not placed in the window
    cannot change the result. Mean and slope use the numeric values in that
    window. Slope is zero when the window has fewer than two numeric points
    or the times do not vary. A column with no numeric value is None.

    Args:
        windows: Windows from :func:`rulsafe.pipeline.windows.build_windows`.
        feature_columns: Explicit allowlist.

    Returns:
        One feature mapping per window, in the same order.

    Raises:
        ConfigurationError: A window has no row sequence, or a name collides.
    """
    lookback_feature_names(feature_columns)
    built: list[dict[str, float | None]] = []
    for window in windows:
        window_rows = window.get("rows")
        if isinstance(window_rows, str) or not isinstance(window_rows, Sequence):
            raise ConfigurationError("A window is missing its rows.")
        mappings = tuple(row for row in window_rows if isinstance(row, Mapping))
        if len(mappings) != len(window_rows):
            raise ConfigurationError("A window row is not a mapping.")
        built.append(_features_for_rows(mappings, feature_columns))
    return built


def _features_for_rows(
    rows: Sequence[Mapping[str, object]],
    feature_columns: Sequence[str],
) -> dict[str, float | None]:
    """Compute last, mean, and slope for one causal window.

    Args:
        rows: Past rows in time order.
        feature_columns: Explicit allowlist.

    Returns:
        Feature name to a float or None.
    """
    points: dict[str, list[tuple[float, float]]] = {column: [] for column in feature_columns}
    for row in rows:
        event_time = _required_time(row, "event_time")
        for column_name in feature_columns:
            numeric = _optional_float(row.get(column_name))
            if numeric is not None:
                points[column_name].append((event_time, numeric))
    features: dict[str, float | None] = {}
    for column_name in feature_columns:
        series = points[column_name]
        features[column_name] = None if not series else series[-1][1]
        features[f"{column_name}_mean"] = _mean(series)
        features[f"{column_name}_slope"] = _slope(series)
    return features


def _mean(series: Sequence[tuple[float, float]]) -> float | None:
    """Return the mean of the numeric window, or None when it is empty.

    Args:
        series: Time and value pairs.

    Returns:
        The arithmetic mean, or None.
    """
    if not series:
        return None
    return sum(value for _, value in series) / len(series)


def _slope(series: Sequence[tuple[float, float]]) -> float | None:
    """Return the least-squares slope of value on event time.

    Args:
        series: Time and value pairs from one causal window.

    Returns:
        None when the column has no numeric value. Zero when one point is
        present or the times do not vary. Otherwise the slope.
    """
    if not series:
        return None
    if len(series) < 2:
        return 0.0
    count = float(len(series))
    mean_time = sum(time for time, _ in series) / count
    mean_value = sum(value for _, value in series) / count
    variance = sum((time - mean_time) ** 2 for time, _ in series)
    if variance == 0.0:
        return 0.0
    covariance = sum((time - mean_time) * (value - mean_value) for time, value in series)
    return covariance / variance


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
