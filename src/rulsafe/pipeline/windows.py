"""Causal windows.

A window for prediction time ``t`` includes only rows that were knowable at
``t``. It does not include a later reading. When ``discard_straddle_split``
is true, a window whose rows name more than one split is dropped.
"""

import math
from collections.abc import Mapping, Sequence

from rulsafe.contract import GapPolicy
from rulsafe.exceptions import ConfigurationError

_RowKey = tuple[float, float, int, Mapping[str, object]]


def build_windows(
    *,
    rows: Sequence[Mapping[str, object]],
    lookback: int,
    stride: int,
    discard_straddle_split: bool,
    prediction_times: Sequence[float] | None = None,
    gap_policy: GapPolicy = GapPolicy.NONE,
    maximum_gap: int | None = None,
) -> tuple[Mapping[str, object], ...]:
    """Build causal lookback windows.

    Each window keeps at most ``lookback`` rows. A row is eligible only when
    its event time and available time are at or before the prediction time.
    Forward fill also drops a row older than ``maximum_gap``. Linear
    interpolation is not available.

    Args:
        rows: Signal rows already limited to one episode.
        lookback: Number of past rows visible at a prediction time.
        stride: Keep every stride-th prediction time, starting at the earliest.
        discard_straddle_split: Drop a window whose rows name more than one split.
        prediction_times: Times to score. The sorted unique event times are
            used when this is omitted.
        gap_policy: ``none`` or bounded forward fill.
        maximum_gap: Largest age of a row kept under forward fill.

    Returns:
        One mapping per kept prediction time, with ``prediction_time`` and
        ``rows``. Rows are in time order and come from the past only.

    Raises:
        ConfigurationError: Lookback, stride, or the forward-fill gap is unusable,
            or a row is missing a time.
    """
    if lookback < 1:
        raise ConfigurationError("lookback must be at least 1.")
    if stride < 1:
        raise ConfigurationError("stride must be at least 1.")
    if gap_policy is GapPolicy.FORWARD_FILL and maximum_gap is None:
        raise ConfigurationError("max_gap is required when gap_policy is ffill.")
    ordered = _ordered_rows(rows)
    times = _selected_times(ordered, prediction_times, stride)
    pointer = 0
    pending: list[_RowKey] = []
    causal: list[_RowKey] = []
    gap_start = 0
    windows: list[dict[str, object]] = []
    for prediction_time in times:
        pointer, pending, causal, resorted = _advance(
            ordered, pointer, pending, causal, prediction_time
        )
        if resorted:
            gap_start = 0
        visible = _visible_rows(
            causal,
            prediction_time,
            gap_policy=gap_policy,
            maximum_gap=maximum_gap,
            gap_start=gap_start,
        )
        gap_start = visible[0]
        chosen = visible[1][-lookback:]
        if discard_straddle_split and _crosses_split(chosen):
            continue
        windows.append(
            {
                "prediction_time": prediction_time,
                "rows": tuple(item[3] for item in chosen),
            }
        )
    return tuple(windows)


def _ordered_rows(rows: Sequence[Mapping[str, object]]) -> tuple[_RowKey, ...]:
    """Sort rows by event time, then by available time.

    Args:
        rows: Signal rows for one episode.

    Returns:
        Decorated rows. The original mapping is the last item.
    """
    decorated: list[_RowKey] = []
    for index, row in enumerate(rows):
        event_time = _required_time(row, "event_time")
        available_at = _required_time(row, "available_at")
        decorated.append((event_time, available_at, index, row))
    decorated.sort()
    return tuple(decorated)


def _selected_times(
    ordered: Sequence[_RowKey],
    prediction_times: Sequence[float] | None,
    stride: int,
) -> tuple[float, ...]:
    """Return the prediction times that receive a window.

    Args:
        ordered: Sorted rows.
        prediction_times: Requested times, or None to use event times.
        stride: Step between kept times.

    Returns:
        Sorted unique times, thinned by ``stride``.
    """
    if prediction_times is None:
        source = tuple(item[0] for item in ordered)
    else:
        source = tuple(float(value) for value in prediction_times)
    unique = tuple(sorted(set(source)))
    return unique[::stride]


def _advance(
    ordered: Sequence[_RowKey],
    pointer: int,
    pending: list[_RowKey],
    causal: list[_RowKey],
    prediction_time: float,
) -> tuple[int, list[_RowKey], list[_RowKey], bool]:
    """Add rows that were knowable at ``prediction_time``.

    A row whose event time has arrived but whose available time has not is
    held until a later prediction time. It is not added early.

    Args:
        ordered: Sorted rows.
        pointer: Index of the next row whose event time has not been considered.
        pending: Rows already seen whose available time is still in the future.
        causal: Knowable rows so far, in time order.
        prediction_time: Time ``t``.

    Returns:
        The new pointer, pending rows, causal rows, and whether the causal
        list was re-sorted.
    """
    while pointer < len(ordered) and ordered[pointer][0] <= prediction_time:
        item = ordered[pointer]
        pointer += 1
        if item[1] <= prediction_time:
            causal.append(item)
        else:
            pending.append(item)
    resorted = False
    if pending:
        still: list[_RowKey] = []
        ready: list[_RowKey] = []
        for item in pending:
            if item[1] <= prediction_time:
                ready.append(item)
            else:
                still.append(item)
        pending = still
        if ready:
            causal.extend(ready)
            causal.sort()
            resorted = True
    return pointer, pending, causal, resorted


def _visible_rows(
    causal: Sequence[_RowKey],
    prediction_time: float,
    *,
    gap_policy: GapPolicy,
    maximum_gap: int | None,
    gap_start: int,
) -> tuple[int, tuple[_RowKey, ...]]:
    """Drop rows that forward fill is not allowed to keep.

    Args:
        causal: Knowable rows in time order.
        prediction_time: Time ``t``.
        gap_policy: ``none`` or bounded forward fill.
        maximum_gap: Largest age kept by forward fill.
        gap_start: First index that might still be inside the gap.

    Returns:
        The index where the visible suffix starts, and that suffix.
    """
    if gap_policy is not GapPolicy.FORWARD_FILL or maximum_gap is None:
        return gap_start, tuple(causal[gap_start:])
    limit = prediction_time - maximum_gap
    start = gap_start
    while start < len(causal) and causal[start][0] < limit:
        start += 1
    return start, tuple(causal[start:])


def _crosses_split(chosen: Sequence[_RowKey]) -> bool:
    """Return whether the window names more than one split.

    Args:
        chosen: Rows in the window.

    Returns:
        True when two different ``split`` values are present. Rows without
        that key do not create a crossing.
    """
    names: set[str] = set()
    for item in chosen:
        row = item[3]
        if "split" not in row:
            continue
        names.add(str(row["split"]))
    return len(names) > 1


def _required_time(row: Mapping[str, object], key: str) -> float:
    """Read a finite time from a signal row.

    Args:
        row: Signal row.
        key: ``event_time`` or ``available_at``.

    Returns:
        The time as a float.

    Raises:
        ConfigurationError: The field is missing, blank, or not finite.
    """
    if key not in row:
        raise ConfigurationError(f"Signal row is missing {key}.")
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ConfigurationError(f"Signal row has a non-numeric {key}.")
    if value == "":
        raise ConfigurationError(f"Signal row has a blank {key}.")
    try:
        number = float(value)
    except ValueError as error:
        raise ConfigurationError(f"Signal row has a non-numeric {key}.") from error
    if not math.isfinite(number):
        raise ConfigurationError(f"Signal row has a non-finite {key}.")
    return number
