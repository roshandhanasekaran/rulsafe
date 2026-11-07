"""Map physical CSV and Parquet files onto assets, signals, and events."""

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
    """Load the configured files and name their contract columns.

    Args:
        config: Validated run configuration.

    Returns:
        Assets, signals, and events using contract column names.

    Raises:
        NotImplementedError: Mapping is not implemented yet.
    """
    raise not_implemented("map_files_to_logical_tables", config)
