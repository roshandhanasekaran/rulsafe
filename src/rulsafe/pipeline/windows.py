"""Causal windows.

A window for prediction time ``t`` includes only rows that were knowable at
``t``. It does not include a later reading, and it does not cross a split
when ``discard_straddle_split`` is true.
"""

from collections.abc import Mapping, Sequence

from rulsafe.exceptions import not_implemented


def build_windows(
    *,
    rows: Sequence[Mapping[str, object]],
    lookback: int,
    stride: int,
    discard_straddle_split: bool,
) -> tuple[Mapping[str, object], ...]:
    """Build causal lookback windows.

    Args:
        rows: Signal rows already limited to one episode.
        lookback: Number of past steps visible at a prediction time.
        stride: Step between successive prediction times.
        discard_straddle_split: Drop windows that cross a train, validation, or test cut.

    Returns:
        One mapping per prediction time.

    Raises:
        NotImplementedError: Windowing is not implemented yet.
    """
    raise not_implemented(
        "build_windows",
        rows,
        lookback,
        stride,
        discard_straddle_split,
    )
