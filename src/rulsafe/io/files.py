"""CSV and Parquet table paths.

CSV files are read here. Parquet is accepted by the contract and still
raises ``NotImplementedError``. An unsupported suffix is rejected.
"""

import csv
from collections.abc import Mapping
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
        rows: One mapping per row. Keys are the header names. CSV values are strings.
    """

    role: LogicalTableRole
    path: Path
    row_count: int
    rows: tuple[Mapping[str, str], ...] = ()


def load_table(path: Path, role: LogicalTableRole) -> LoadedTable:
    """Load a CSV or Parquet file into a logical table.

    Args:
        path: Table path. The suffix is checked before the body is read.
        role: Contract role the file is supposed to fill.

    Returns:
        The loaded table.

    Raises:
        ConfigurationError: The suffix is not supported, or the CSV cannot be read.
        NotImplementedError: The file is Parquet. That reader is not implemented yet.
    """
    if not table_suffix_is_supported(path):
        raise ConfigurationError(
            f"Unsupported table file {path.name}. Expected a .csv or .parquet file."
        )
    if path.suffix.casefold() == ".parquet":
        raise not_implemented("load_table", path, role)
    if not path.is_file():
        raise ConfigurationError(f"Could not read table file {path}.")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(f"Could not read table file {path}.") from error
    rows = tuple(_csv_rows(text, path))
    if not rows:
        raise ConfigurationError(f"Table file {path} has no data rows.")
    return LoadedTable(role=role, path=path, row_count=len(rows), rows=rows)


def _csv_rows(text: str, path: Path) -> tuple[Mapping[str, str], ...]:
    """Parse CSV text into row mappings.

    Args:
        text: Full file text.
        path: Path used in error messages.

    Returns:
        One mapping per data row.

    Raises:
        ConfigurationError: The header is missing or a row is not a mapping.
    """
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise ConfigurationError(f"Table file {path} has no header.")
    parsed: list[Mapping[str, str]] = []
    for row in reader:
        if row is None:
            continue
        parsed.append({str(key): "" if value is None else str(value) for key, value in row.items()})
    return tuple(parsed)
