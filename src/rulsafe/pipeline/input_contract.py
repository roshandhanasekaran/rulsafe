"""Runtime checks for configured Assets, Readings, and Events tables."""

import math
from collections import Counter
from collections.abc import Sequence

from rulsafe.config import RunConfig
from rulsafe.exceptions import ConfigurationError
from rulsafe.io.files import LoadedTable
from rulsafe.mapping import LogicalTables


def validate_table_contract(tables: LogicalTables, config: RunConfig) -> None:
    """Reject malformed physical tables before any split or model is fit.

    Args:
        tables: Loaded assets, signals, and events.
        config: Configuration after automatic features have been resolved.

    Raises:
        ConfigurationError: A configured column is absent, an identifier is
            blank or duplicated, or a numeric cell is invalid.
    """
    signal_features = config.signals.feature_columns
    if not isinstance(signal_features, list):
        raise ConfigurationError("feature_columns: auto is not resolved in this run yet.")
    _require_columns(
        tables.assets,
        (config.assets.id_column, *config.assets.extra_columns),
    )
    _require_columns(
        tables.signals,
        (
            config.signals.id_column,
            config.signals.event_time_column,
            *(
                (config.signals.available_at_column,)
                if config.signals.available_at_column is not None
                else ()
            ),
            *signal_features,
        ),
    )
    _require_columns(
        tables.events,
        (
            config.events.id_column,
            config.events.event_time_column,
            *(
                (config.events.available_at_column,)
                if config.events.available_at_column is not None
                else ()
            ),
            config.events.type_column,
        ),
    )
    _require_asset_identifiers(tables.assets, config.assets.id_column)
    _require_nonblank_column(tables.signals, config.signals.id_column)
    _require_nonblank_column(tables.events, config.events.id_column)
    _require_nonblank_column(tables.events, config.events.type_column)
    _require_finite_times(
        tables.signals,
        event_time_column=config.signals.event_time_column,
        available_at_column=config.signals.available_at_column,
    )
    _require_finite_times(
        tables.events,
        event_time_column=config.events.event_time_column,
        available_at_column=config.events.available_at_column,
    )
    _require_finite_features(tables.signals, signal_features)


def _require_columns(table: LoadedTable, names: Sequence[str]) -> None:
    """Require configured columns on one loaded table."""
    columns = set(table.rows[0])
    missing = sorted(set(names) - columns)
    if missing:
        raise ConfigurationError(
            f"{table.role.value} table {table.path} is missing configured columns: "
            + ", ".join(missing)
            + "."
        )


def _require_asset_identifiers(table: LoadedTable, column_name: str) -> None:
    """Require one non-blank, unique identifier per asset row."""
    identifiers = [row[column_name].strip() for row in table.rows]
    if any(not identifier for identifier in identifiers):
        raise ConfigurationError(f"assets table {table.path} has a blank {column_name}.")
    duplicates = sorted(
        identifier for identifier, count in Counter(identifiers).items() if count > 1
    )
    if duplicates:
        raise ConfigurationError(
            f"assets table {table.path} repeats {column_name} values: "
            + ", ".join(duplicates)
            + "."
        )


def _require_nonblank_column(table: LoadedTable, column_name: str) -> None:
    """Reject a blank required cell with a table-specific error."""
    for row_number, row in enumerate(table.rows, start=2):
        if not row[column_name].strip():
            raise ConfigurationError(
                f"{table.role.value} table {table.path} row {row_number} has a blank {column_name}."
            )


def _require_finite_times(
    table: LoadedTable,
    *,
    event_time_column: str,
    available_at_column: str | None,
) -> None:
    """Require finite times and prevent records from predating themselves."""
    for row_number, row in enumerate(table.rows, start=2):
        event_time = _finite_cell(table, row_number, event_time_column, row[event_time_column])
        if available_at_column is None:
            continue
        available_at = _finite_cell(
            table, row_number, available_at_column, row[available_at_column]
        )
        if available_at < event_time:
            raise ConfigurationError(
                f"{table.role.value} table {table.path} row {row_number} has "
                f"{available_at_column} earlier than {event_time_column}."
            )


def _require_finite_features(table: LoadedTable, feature_columns: Sequence[str]) -> None:
    """Require every non-blank feature cell to be a finite number."""
    for row_number, row in enumerate(table.rows, start=2):
        for column_name in feature_columns:
            if row[column_name].strip() == "":
                continue
            _finite_cell(table, row_number, column_name, row[column_name])


def _finite_cell(table: LoadedTable, row_number: int, column_name: str, value: str) -> float:
    """Parse one finite table cell with a stable configuration error."""
    try:
        number = float(value)
    except ValueError as error:
        raise ConfigurationError(
            f"{table.role.value} table {table.path} row {row_number} "
            f"has a non-numeric {column_name}."
        ) from error
    if not math.isfinite(number):
        raise ConfigurationError(
            f"{table.role.value} table {table.path} row {row_number} "
            f"has a non-finite {column_name}."
        )
    return number
