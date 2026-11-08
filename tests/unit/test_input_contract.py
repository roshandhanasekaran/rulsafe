"""Physical-table checks that run before fitting."""

from pathlib import Path

import pytest

from rulsafe.config import RunConfig
from rulsafe.contract import LogicalTableRole
from rulsafe.exceptions import ConfigurationError
from rulsafe.io.files import LoadedTable
from rulsafe.mapping import LogicalTables
from rulsafe.pipeline.input_contract import validate_table_contract


def test_valid_contract_allows_delays_blanks_and_constant_features(load_example) -> None:
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    tables = _tables(
        signals=(
            {
                "asset_id": "unit-a",
                "event_time": "0",
                "available_at": "2",
                "temperature": "",
                "pressure": "1",
            },
        )
    )
    validate_table_contract(tables, config)


@pytest.mark.parametrize(
    ("table_name", "column_name"),
    [
        ("assets", "asset_id"),
        ("signals", "pressure"),
        ("events", "event_type"),
    ],
)
def test_configured_columns_must_exist(load_example, table_name: str, column_name: str) -> None:
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    tables = _tables()
    table = getattr(tables, table_name)
    stripped = tuple(
        {name: value for name, value in row.items() if name != column_name} for row in table.rows
    )
    changed = LoadedTable(table.role, table.path, len(stripped), stripped)
    tables = LogicalTables(
        assets=changed if table_name == "assets" else tables.assets,
        signals=changed if table_name == "signals" else tables.signals,
        events=changed if table_name == "events" else tables.events,
    )
    with pytest.raises(ConfigurationError, match=rf"missing configured columns: {column_name}"):
        validate_table_contract(tables, config)


@pytest.mark.parametrize(
    ("identifiers", "message"),
    [
        (("unit-a", ""), "blank asset_id"),
        (("unit-a", " unit-a "), "repeats asset_id values: unit-a"),
    ],
)
def test_asset_identifiers_are_nonblank_and_unique(
    load_example, identifiers: tuple[str, str], message: str
) -> None:
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    assets = tuple({"asset_id": identifier} for identifier in identifiers)
    with pytest.raises(ConfigurationError, match=message):
        validate_table_contract(_tables(assets=assets), config)


@pytest.mark.parametrize(
    ("table_name", "column_name"),
    [
        ("signals", "asset_id"),
        ("events", "asset_id"),
        ("events", "event_type"),
    ],
)
def test_required_row_cells_cannot_be_blank(
    load_example, table_name: str, column_name: str
) -> None:
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    tables = _tables()
    table = getattr(tables, table_name)
    changed_rows = tuple({**row, column_name: " "} for row in table.rows)
    changed = LoadedTable(table.role, table.path, len(changed_rows), changed_rows)
    tables = LogicalTables(
        assets=tables.assets,
        signals=changed if table_name == "signals" else tables.signals,
        events=changed if table_name == "events" else tables.events,
    )
    with pytest.raises(ConfigurationError, match=rf"blank {column_name}"):
        validate_table_contract(tables, config)


@pytest.mark.parametrize(
    ("table_name", "column_name", "value", "message"),
    [
        ("signals", "event_time", "bad", "non-numeric event_time"),
        ("events", "event_time", "nan", "non-finite event_time"),
        ("signals", "temperature", "inf", "non-finite temperature"),
        ("signals", "available_at", "-1", "available_at earlier than event_time"),
    ],
)
def test_times_and_features_must_be_finite_and_causal(
    load_example,
    table_name: str,
    column_name: str,
    value: str,
    message: str,
) -> None:
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    tables = _tables()
    table = getattr(tables, table_name)
    changed_rows = tuple({**row, column_name: value} for row in table.rows)
    changed = LoadedTable(table.role, table.path, len(changed_rows), changed_rows)
    tables = LogicalTables(
        assets=tables.assets,
        signals=changed if table_name == "signals" else tables.signals,
        events=changed if table_name == "events" else tables.events,
    )
    with pytest.raises(ConfigurationError, match=message):
        validate_table_contract(tables, config)


def test_auto_features_must_be_resolved_before_contract_validation(load_example) -> None:
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    unresolved = config.model_copy(
        update={"signals": config.signals.model_copy(update={"feature_columns": "auto"})}
    )
    with pytest.raises(ConfigurationError, match="auto is not resolved"):
        validate_table_contract(_tables(), unresolved)


def _tables(
    *,
    assets: tuple[dict[str, str], ...] | None = None,
    signals: tuple[dict[str, str], ...] | None = None,
    events: tuple[dict[str, str], ...] | None = None,
) -> LogicalTables:
    asset_rows = assets or ({"asset_id": "unit-a"},)
    signal_rows = signals or (
        {
            "asset_id": "unit-a",
            "event_time": "0",
            "available_at": "0",
            "temperature": "10",
            "pressure": "1",
        },
    )
    event_rows = events or (
        {
            "asset_id": "unit-a",
            "event_time": "1",
            "available_at": "1",
            "event_type": "failure",
            "failure_notes": "bearing",
        },
    )
    return LogicalTables(
        assets=LoadedTable(
            LogicalTableRole.ASSETS, Path("assets.csv"), len(asset_rows), asset_rows
        ),
        signals=LoadedTable(
            LogicalTableRole.SIGNALS, Path("signals.csv"), len(signal_rows), signal_rows
        ),
        events=LoadedTable(
            LogicalTableRole.EVENTS, Path("events.csv"), len(event_rows), event_rows
        ),
    )
