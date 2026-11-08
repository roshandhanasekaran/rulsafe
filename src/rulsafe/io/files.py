"""CSV and Parquet table paths.

CSV and Parquet files are read here. An unsupported suffix is rejected.
Parquet cells are converted to strings so the rest of the pipeline sees the
same kind of row it sees from CSV.
"""

import csv
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from rulsafe.contract import LogicalTableRole, table_suffix_is_supported
from rulsafe.exceptions import ConfigurationError


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
        ConfigurationError: The suffix is not supported, or the table cannot be read.
    """
    if not table_suffix_is_supported(path):
        raise ConfigurationError(
            f"Unsupported table file {path.name}. Expected a .csv or .parquet file."
        )
    if path.suffix.casefold() == ".parquet":
        rows = _parquet_rows(path)
        if not rows:
            raise ConfigurationError(f"Table file {path} has no data rows.")
        return LoadedTable(role=role, path=path, row_count=len(rows), rows=rows)
    if not path.is_file():
        raise ConfigurationError(f"Could not read table file {path}.")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError as error:
        raise ConfigurationError(f"Table file {path} is not valid UTF-8.") from error
    except OSError as error:
        raise ConfigurationError(f"Could not read table file {path}.") from error
    rows = tuple(_csv_rows(text, path))
    if not rows:
        raise ConfigurationError(f"Table file {path} has no data rows.")
    return LoadedTable(role=role, path=path, row_count=len(rows), rows=rows)


def _parquet_rows(path: Path) -> tuple[Mapping[str, str], ...]:
    """Read a Parquet file into string rows.

    Args:
        path: Parquet path.

    Returns:
        One mapping per row. Column order follows the file schema.

    Raises:
        ConfigurationError: The file cannot be read.
    """
    if not path.is_file():
        raise ConfigurationError(f"Could not read table file {path}.")
    try:
        import pyarrow.parquet as parquet  # type: ignore[import-untyped]
    except ImportError as error:
        raise ConfigurationError("Reading Parquet requires pyarrow.") from error
    try:
        parquet_file = parquet.ParquetFile(path)
        names = list(parquet_file.schema_arrow.names)
    except Exception as error:
        raise ConfigurationError(f"Could not read table file {path}.") from error
    _require_valid_column_names(names, path)
    try:
        table = parquet_file.read()
    except Exception as error:
        raise ConfigurationError(f"Could not read table file {path}.") from error
    parsed: list[Mapping[str, str]] = []
    for record in table.to_pylist():
        if not isinstance(record, dict):
            raise ConfigurationError(f"Table file {path} has a row that is not a mapping.")
        parsed.append(
            {name: "" if record.get(name) is None else str(record.get(name)) for name in names}
        )
    return tuple(parsed)


def _csv_rows(text: str, path: Path) -> tuple[Mapping[str, str], ...]:
    """Parse CSV text into row mappings.

    Args:
        text: Full file text.
        path: Path used in error messages.

    Returns:
        One mapping per data row.

    Raises:
        ConfigurationError: The header is missing or ambiguous, or a row has
            a different number of cells from the header.
    """
    try:
        reader = csv.reader(StringIO(text, newline=""), strict=True)
        fieldnames = next(reader, None)
        if not fieldnames:
            raise ConfigurationError(f"Table file {path} has no header.")
        _require_valid_column_names(fieldnames, path)
        parsed: list[Mapping[str, str]] = []
        for row_number, row in enumerate(reader, start=2):
            if not row:
                continue
            if len(row) != len(fieldnames):
                raise ConfigurationError(
                    f"Table file {path} row {row_number} has {len(row)} cells; "
                    f"the header has {len(fieldnames)}."
                )
            parsed.append(dict(zip(fieldnames, row, strict=True)))
        return tuple(parsed)
    except csv.Error as error:
        raise ConfigurationError(f"Could not parse CSV table file {path}.") from error


def _require_valid_column_names(names: list[str], path: Path) -> None:
    """Reject blank or duplicate physical column names before row mapping."""
    if any(not name.strip() for name in names):
        raise ConfigurationError(f"Table file {path} has a blank column name.")
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        raise ConfigurationError(
            f"Table file {path} has duplicate column names: " + ", ".join(duplicates) + "."
        )
