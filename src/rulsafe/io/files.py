"""CSV and Parquet table paths.

Loading the bytes is not implemented yet. The suffix check is implemented
so an unsupported file is rejected instead of being ignored.
"""

from dataclasses import dataclass
from pathlib import Path

from rulsafe.contract import LogicalTableRole, table_suffix_is_supported
from rulsafe.exceptions import ConfigurationError, not_implemented


@dataclass(frozen=True)
class LoadedTable:
    """A logical table after a file has been read.

    Attributes:
        role: Which contract role this file fills.
        path: Source path.
        row_count: Number of rows in the file.
    """

    role: LogicalTableRole
    path: Path
    row_count: int


def load_table(path: Path, role: LogicalTableRole) -> LoadedTable:
    """Load a CSV or Parquet file into a logical table.

    Args:
        path: Table path. The suffix is checked. The body is not read yet.
        role: Contract role the file is supposed to fill.

    Returns:
        The loaded table.

    Raises:
        ConfigurationError: The suffix is not ``.csv`` or ``.parquet``.
        NotImplementedError: Reading the file is not implemented yet.
    """
    if not table_suffix_is_supported(path):
        raise ConfigurationError(
            f"Unsupported table file {path.name}. Expected a .csv or .parquet file."
        )
    raise not_implemented("load_table", path, role)
