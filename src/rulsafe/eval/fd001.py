"""FD001 last-observation protocol and the piecewise RUL cap.

The official test score uses one prediction per ``test_FD001`` engine, at
that engine's last observed cycle. Truth is ``RUL_FD001.txt``. Those values
are not training labels. Validation for the same protocol is the last
pre-failure cycle of each held-out training engine. Early stopping stays on
every causal row of those engines.

The NASA score is the Saxena 2008 sum of one term per engine. It is not a
sum over rows.
"""

import math
from pathlib import Path

from rulsafe.exceptions import ConfigurationError

FD001_PROTOCOL_NAME = "fd001_last_observation"
HELD_OUT_ROWS_PROTOCOL_NAME = "held_out_engine_rows"
NASA_SCORE_DEFINITION = (
    "Saxena 2008: d is predicted remaining life minus true remaining life "
    "at the engine's scored time. Early (d < 0) contributes exp(-d/13) - 1. "
    "Late contributes exp(d/10) - 1. The score sums one term per engine. "
    "It is not summed over rows, and it is not a gate."
)


def cap_remaining_life(value: float, rul_cap: int | None) -> float:
    """Apply the piecewise cap ``min(remaining life, cap)``.

    Args:
        value: Remaining life before the cap.
        rul_cap: Positive cap, or None when the target is left unchanged.

    Returns:
        The capped value. ``None`` returns ``value``.
    """
    if rul_cap is None:
        return value
    return min(value, float(rul_cap))


def read_official_rul(path: Path) -> dict[str, float]:
    """Read asset id and official remaining life from the converted RUL file.

    Each non-blank line is ``asset_id value``. The value is the truth for
    that engine's last observed cycle. It is not copied into a training label.

    Args:
        path: ``fd001_official_rul.txt``, or another file in that form.

    Returns:
        Asset id to remaining life, in file order.

    Raises:
        ConfigurationError: The file is missing, blank, or not paired values.
    """
    if not path.is_file():
        raise ConfigurationError(f"Official RUL file {path} is not on disk.")
    found: dict[str, float] = {}
    text = path.read_text(encoding="utf-8")
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        cells = raw_line.split()
        if not cells:
            continue
        if len(cells) != 2:
            raise ConfigurationError(
                f"Official RUL file {path} line {line_number} must be an asset id and a value."
            )
        asset_id, token = cells
        if asset_id in found:
            raise ConfigurationError(f"Official RUL file {path} repeats {asset_id}.")
        try:
            value = float(token)
        except ValueError as error:
            raise ConfigurationError(
                f"Official RUL file {path} line {line_number} has a non-numeric value."
            ) from error
        if not math.isfinite(value):
            raise ConfigurationError(
                f"Official RUL file {path} line {line_number} has a non-finite value."
            )
        found[asset_id] = value
    if not found:
        raise ConfigurationError(f"Official RUL file {path} has no rows.")
    return found


def protocol_description(*, official: bool, rul_cap: int | None) -> str:
    """Describe the evaluation that this run actually scores.

    Args:
        official: True when the FD001 last-observation benchmark is configured.
        rul_cap: Piecewise cap, or None.

    Returns:
        The protocol paragraph stored in the report.
    """
    cap_text = "none" if rul_cap is None else str(rul_cap)
    cap_sentence = (
        f"Piecewise RUL cap (target.rul_cap): {cap_text}. "
        "When the cap is set, every supervised target and every official truth "
        "is min(remaining life, cap) before fit and score."
    )
    if not official:
        return (
            "Held-out engine rows. The headline evaluation is the test split of "
            "the model selected on validation root_mean_square_error. Validation "
            "metrics are used for early stopping/selection and are optimistic "
            "relative to the test. No official FD001 RUL file is configured. "
            f"{cap_sentence} {NASA_SCORE_DEFINITION}"
        )
    return (
        "Official FD001 benchmark. Score the last observation of each official "
        "test_FD001 engine against RUL_FD001.txt. Truth is the remaining cycles "
        "after that cycle. Validation for this protocol is the last pre-failure "
        "cycle of each held-out training engine, with truth equal to the cycles "
        "remaining until failure. The model is fit on earlier training engines "
        "only. Early stopping and model selection use every causal row of the "
        "held-out training engines and do not read the official RUL file. "
        "The per-row scores on those held-out completed training engines are a "
        "secondary view, not the official benchmark. "
        f"{cap_sentence} {NASA_SCORE_DEFINITION}"
    )
