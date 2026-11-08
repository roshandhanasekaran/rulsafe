"""Logical-table container and a reserved mapping adapter.

The v0.1 public pipeline loads and maps CSV/Parquet inputs in
``rulsafe.pipeline.execute``.  ``map_files_to_logical_tables`` is an internal
placeholder kept for a future standalone mapping API; the public pipeline does
not call it.
"""

from dataclasses import dataclass

from rulsafe.config import RunConfig
from rulsafe.exceptions import not_implemented
from rulsafe.io.files import LoadedTable


@dataclass(frozen=True)
class LogicalTables:
    """The three logical tables for one run.

    Attributes:
        assets: One row per piece of equipment.
        signals: Telemetry or cycle readings.
        events: Terminal and competing events, when the trajectory has them.
    """

    assets: LoadedTable
    signals: LoadedTable
    events: LoadedTable


def map_files_to_logical_tables(config: RunConfig) -> LogicalTables:
    """Reserved adapter for a future standalone file-mapping API.

    Args:
        config: Validated run configuration.

    Returns:
        Assets, signals, and events using contract column names.

    Raises:
        NotImplementedError: This reserved adapter is not implemented.
    """
    raise not_implemented("map_files_to_logical_tables", config)
