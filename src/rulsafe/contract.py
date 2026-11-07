"""Data-contract vocabulary: tables, time fields, gap policy, and episode rules.

These types describe the contract. They do not read files or build windows.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from rulsafe.exceptions import ConfigurationError

SUPPORTED_TABLE_SUFFIXES: tuple[str, ...] = (".csv", ".parquet")


class LogicalTableRole(StrEnum):
    """One of the three logical tables every run maps files onto."""

    ASSETS = "assets"
    SIGNALS = "signals"
    EVENTS = "events"


class TimeField(StrEnum):
    """A time column in the data contract."""

    EVENT_TIME = "event_time"
    AVAILABLE_AT = "available_at"
    OBSERVATION_START = "observation_start"
    OBSERVATION_END = "observation_end"


class TimestampType(StrEnum):
    """Unit in which time columns are compared."""

    DATETIME = "datetime"
    CYCLE = "cycle"
    INTEGER_STEP = "integer_step"


class GapPolicy(StrEnum):
    """How missing signal values are treated.

    Linear interpolation is intentionally absent. Filling a time from a later
    reading uses the future, which this package exists to reject.
    """

    NONE = "none"
    FORWARD_FILL = "ffill"


TIME_FIELD_DEFINITIONS: dict[TimeField, str] = {
    TimeField.EVENT_TIME: "When the fact happened in the world.",
    TimeField.AVAILABLE_AT: (
        "The earliest time an online model could have known the record. "
        "A row used at prediction time t with available_at later than t is leakage."
    ),
    TimeField.OBSERVATION_START: (
        "When this episode of the component begins, such as install or the start after replacement."
    ),
    TimeField.OBSERVATION_END: (
        "When observation of this episode stops, because collection ends, the asset leaves, "
        "or a terminal event closes the episode."
    ),
}

REQUIRED_COLUMNS: dict[LogicalTableRole, tuple[str, ...]] = {
    LogicalTableRole.ASSETS: ("asset_id",),
    LogicalTableRole.SIGNALS: ("asset_id", "event_time"),
    LogicalTableRole.EVENTS: ("asset_id", "event_time", "event_type"),
}

IDENTIFIER_COLUMN_NAMES: frozenset[str] = frozenset(
    {
        "asset_id",
        "vehicle_id",
        "vin",
        "serial",
        "serial_number",
        "engine_id",
        "unit_id",
    }
)

TARGET_COLUMN_NAMES: frozenset[str] = frozenset(
    {
        "label",
        "target",
        "rul",
        "remaining_useful_life",
        "failure_within_horizon",
    }
)

_INTERPOLATION_POLICIES: frozenset[str] = frozenset(
    {
        "linear",
        "interpolate",
        "interpolation",
        "linear_interpolation",
        "interp",
    }
)

_RANDOM_PROTOCOL = "random"


def table_suffix_is_supported(path: Path) -> bool:
    """Return whether a path names a CSV or Parquet table.

    Args:
        path: Candidate table path. The file does not need to exist.

    Returns:
        True when the suffix is ``.csv`` or ``.parquet``.
    """
    return path.suffix.casefold() in SUPPORTED_TABLE_SUFFIXES


def required_columns(role: LogicalTableRole) -> tuple[str, ...]:
    """Return the columns a logical table must contain.

    Args:
        role: Which logical table is being checked.

    Returns:
        Column names in contract order. Physical files may use other headers
        before they are mapped onto these names.
    """
    return REQUIRED_COLUMNS[role]


def column_is_identifier(column_name: str, identifier_column: str) -> bool:
    """Return whether a column is an equipment identifier.

    Args:
        column_name: Candidate feature column.
        identifier_column: The configured asset identifier column.

    Returns:
        True when the column is the identifier column or a known identifier name.
    """
    folded_name = column_name.casefold()
    return folded_name == identifier_column.casefold() or folded_name in IDENTIFIER_COLUMN_NAMES


def column_is_target_name(column_name: str) -> bool:
    """Return whether a column name is an obvious label or target.

    Args:
        column_name: Candidate feature column.

    Returns:
        True when the name matches the reserved target names.
    """
    return column_name.casefold() in TARGET_COLUMN_NAMES


def parse_gap_policy(raw_policy: str) -> GapPolicy:
    """Parse a gap policy and reject non-causal interpolation.

    Args:
        raw_policy: Value of ``signals.gap_policy``.

    Returns:
        The accepted gap policy.

    Raises:
        ConfigurationError: The policy is linear interpolation or is unknown.
    """
    normalized = raw_policy.strip().casefold()
    if normalized in _INTERPOLATION_POLICIES:
        raise ConfigurationError(
            "Linear interpolation is not available. It fills an earlier time with a later "
            "reading, which is leakage. Use gap_policy none or ffill."
        )
    try:
        return GapPolicy(normalized)
    except ValueError as error:
        raise ConfigurationError(
            f"Unknown gap policy {raw_policy!r}. Use none or ffill."
        ) from error


def reject_random_split(protocol_name: str) -> str:
    """Reject a shuffled panel split.

    Args:
        protocol_name: Raw protocol or legacy ``split.type`` value.

    Returns:
        The stripped protocol name when it is not ``random``.

    Raises:
        ConfigurationError: The name selects a random split.
    """
    normalized = protocol_name.strip().casefold()
    if normalized == _RANDOM_PROTOCOL:
        raise ConfigurationError(
            "A random split of the panel is not allowed. "
            "Choose official_partitions or group_holdout. global_time is deferred to v0.2."
        )
    return normalized


@dataclass(frozen=True)
class EpisodeRule:
    """How replacements close one episode and open the next.

    Attributes:
        replacement_starts_new_episode: When true, a replacement must not be
            crossed by a window, a label, or a feature.
        replacement_event_types: Event types that close the current episode.
    """

    replacement_starts_new_episode: bool = True
    replacement_event_types: tuple[str, ...] = ()


def episode_rule(
    *,
    replacement_starts_new_episode: bool = True,
    replacement_event_types: Sequence[str] = (),
) -> EpisodeRule:
    """Build an episode rule, defaulting to a new episode after replacement.

    Args:
        replacement_starts_new_episode: Whether replacement opens a new episode.
        replacement_event_types: Event types that count as replacements.

    Returns:
        The episode rule.
    """
    return EpisodeRule(
        replacement_starts_new_episode=replacement_starts_new_episode,
        replacement_event_types=tuple(replacement_event_types),
    )
