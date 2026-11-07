"""Train, validation, and final-test splits.

``random`` is not a protocol. Choices, including which baseline is the
headline, are made on validation. The final test is scored once after that
choice is frozen.
"""

from enum import Enum

from rulsafe.config import SplitProtocol
from rulsafe.exceptions import not_implemented


class SplitName(str, Enum):
    """One of the three splits every run has."""

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


def assign_splits(protocol: SplitProtocol) -> dict[SplitName, tuple[str, ...]]:
    """Assign each entity to train, validation, or final test.

    Args:
        protocol: ``official_partitions``, ``global_time``, or ``group_holdout``.

    Returns:
        Entity identifiers by split. A group appears in only one split when
        the protocol is group holdout or official partitions.

    Raises:
        NotImplementedError: Splitting is not implemented yet.
    """
    raise not_implemented("assign_splits", protocol)
