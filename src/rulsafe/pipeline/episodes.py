"""Episode construction.

A terminal failure completes the episode. A competing close, such as leaving
the study, censors it. The censored asset is kept and classified. It is not
removed.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from rulsafe.config import RunConfig
from rulsafe.exceptions import ConfigurationError
from rulsafe.mapping import LogicalTables
from rulsafe.pipeline.labels import HistorySupport


@dataclass(frozen=True)
class Episode:
    """One asset history after the replacement and censoring rules.

    Attributes:
        asset_id: Equipment identifier.
        support: Whether v0.1 can score this history.
        end_time: Failure time for a completed history, otherwise the close time.
        rows: Signal rows normalized to ``event_time``, ``available_at``, and features.
    """

    asset_id: str
    support: HistorySupport
    end_time: float | None
    rows: tuple[Mapping[str, object], ...]


def build_episodes(tables: LogicalTables, config: RunConfig) -> tuple[Episode, ...]:
    """Build one episode per asset from the logical tables.

    Args:
        tables: Loaded assets, signals, and events.
        config: Validated run configuration.

    Returns:
        Episodes in asset-id order. Censored assets are included.
    """
    asset_ids = _column_values(tables.assets.rows, config.assets.id_column)
    signals_by_asset = _group_rows(tables.signals.rows, config.signals.id_column)
    events_by_asset = _group_rows(tables.events.rows, config.events.id_column)
    episodes: list[Episode] = []
    for asset_id in asset_ids:
        episodes.append(
            _episode_for_asset(
                asset_id,
                signals_by_asset.get(asset_id, ()),
                events_by_asset.get(asset_id, ()),
                config,
            )
        )
    return tuple(episodes)


def _episode_for_asset(
    asset_id: str,
    signal_rows: tuple[Mapping[str, str], ...],
    event_rows: tuple[Mapping[str, str], ...],
    config: RunConfig,
) -> Episode:
    """Classify one asset and keep its signal rows.

    Args:
        asset_id: Equipment identifier.
        signal_rows: Rows for this asset.
        event_rows: Events for this asset.
        config: Validated run configuration.

    Returns:
        The episode, including a censored or unsupported one.
    """
    failure_time = _earliest_event_time(event_rows, config.events.terminal_types, config)
    censor_time = _earliest_event_time(event_rows, config.events.competing_types, config)
    if failure_time is not None:
        support = HistorySupport.COMPLETED
        end_time: float | None = failure_time
    elif censor_time is not None:
        support = HistorySupport.CENSORED
        end_time = censor_time
    else:
        support = HistorySupport.UNSUPPORTED
        end_time = None
    return Episode(
        asset_id=asset_id,
        support=support,
        end_time=end_time,
        rows=tuple(_normalize_signal(row, config) for row in signal_rows),
    )


def _normalize_signal(row: Mapping[str, str], config: RunConfig) -> dict[str, object]:
    """Rename configured signal columns onto the contract names.

    Args:
        row: Raw signal row.
        config: Validated run configuration.

    Returns:
        A row with ``event_time``, ``available_at``, and the allowlisted features.
    """
    event_time = row.get(config.signals.event_time_column, "")
    if config.signals.available_at_column is None:
        available_at = event_time
    else:
        available_at = row.get(config.signals.available_at_column, "")
    normalized: dict[str, object] = {"event_time": event_time, "available_at": available_at}
    feature_columns = config.signals.feature_columns
    if feature_columns == "auto":
        raise ConfigurationError("feature_columns: auto is not resolved in this run yet.")
    for column_name in feature_columns:
        normalized[column_name] = row.get(column_name, "")
    return normalized


def _earliest_event_time(
    rows: tuple[Mapping[str, str], ...],
    event_types: list[str],
    config: RunConfig,
) -> float | None:
    """Return the earliest time of one of the named event types.

    Args:
        rows: Event rows for one asset.
        event_types: Types to consider.
        config: Column names.

    Returns:
        The earliest numeric time, or None when no row matches.
    """
    wanted = {event_type.casefold() for event_type in event_types}
    times: list[float] = []
    for row in rows:
        event_type = row.get(config.events.type_column, "").casefold()
        if event_type not in wanted:
            continue
        raw_time = row.get(config.events.event_time_column, "")
        if raw_time == "":
            raise ConfigurationError("An event row is missing its event time.")
        times.append(float(raw_time))
    if not times:
        return None
    return min(times)


def _column_values(rows: tuple[Mapping[str, str], ...], column_name: str) -> tuple[str, ...]:
    """Return non-blank values of one column, in file order, without duplicates.

    Args:
        rows: Table rows.
        column_name: Header to read.

    Returns:
        Unique values.
    """
    seen: list[str] = []
    for row in rows:
        value = row.get(column_name, "").strip()
        if value and value not in seen:
            seen.append(value)
    return tuple(seen)


def _group_rows(
    rows: tuple[Mapping[str, str], ...],
    column_name: str,
) -> dict[str, tuple[Mapping[str, str], ...]]:
    """Group rows by an identifier column.

    Args:
        rows: Table rows.
        column_name: Identifier header.

    Returns:
        Identifier to the rows that carry it.
    """
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        identifier = row.get(column_name, "").strip()
        if not identifier:
            continue
        grouped.setdefault(identifier, []).append(row)
    return {identifier: tuple(grouped_rows) for identifier, grouped_rows in grouped.items()}
