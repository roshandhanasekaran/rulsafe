"""Local file loading.

v0.1 reads CSV and Parquet only. Warehouse connectors are out of scope.
"""

from rulsafe.io.files import LoadedTable as LoadedTable
from rulsafe.io.files import load_table as load_table

__all__ = ["LoadedTable", "load_table"]
