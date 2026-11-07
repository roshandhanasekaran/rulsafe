"""Episode construction.

A replacement closes the current episode and opens the next one when the
contract says so. Windows must not cross that boundary.
"""

from rulsafe.config import ContractConfig
from rulsafe.exceptions import not_implemented
from rulsafe.mapping import LogicalTables


def build_episodes(tables: LogicalTables, contract: ContractConfig) -> tuple[str, ...]:
    """Build episode identifiers from assets, events, and the replacement rule.

    Args:
        tables: Logical assets, signals, and events.
        contract: Observation bounds and replacement types.

    Returns:
        Episode identifiers. The concrete row type is added with the implementation.

    Raises:
        NotImplementedError: Episode construction is not implemented yet.
    """
    raise not_implemented("build_episodes", tables, contract)
