"""Train, validation, and final-test splits.

``random`` is not a protocol. ``global_time`` is deferred to v0.2.
``group_holdout`` assigns each asset to one split. Choices, including which
baseline is the headline, are made on validation. The final test is scored
once after that choice is frozen.
"""

import random
from collections.abc import Mapping, Sequence
from enum import Enum

from rulsafe.config import SplitProtocol
from rulsafe.exceptions import ConfigurationError, not_implemented

# One asset is the smallest split that can still be scored. Fewer than this
# is recorded as a report risk. An empty split is the count of zero.
MINIMUM_SPLIT_ASSET_COUNT = 1


class SplitName(str, Enum):
    """One of the three splits every run has."""

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


def assign_splits(
    protocol: SplitProtocol,
    *,
    group_identifiers: Sequence[str],
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    seed: int,
) -> dict[SplitName, tuple[str, ...]]:
    """Assign each entity to train, validation, or final test.

    Args:
        protocol: ``official_partitions`` or ``group_holdout``.
        group_identifiers: Asset or group ids. Duplicates are ignored.
        train_ratio: Share of groups for train.
        validation_ratio: Share of groups for validation.
        test_ratio: Share of groups for the final test.
        seed: Shuffle seed. The same seed and ids always give the same split.

    Returns:
        Entity identifiers by split. Each id appears in one split.

    Raises:
        NotImplementedError: ``official_partitions`` is not implemented yet.
        ConfigurationError: The ratios do not describe a split of these groups.
    """
    if protocol is not SplitProtocol.GROUP_HOLDOUT:
        raise not_implemented(
            "assign_splits",
            protocol,
            group_identifiers,
            train_ratio,
            validation_ratio,
            test_ratio,
            seed,
        )
    identifiers = tuple(dict.fromkeys(group_identifiers))
    counts = _largest_remainder_counts(
        len(identifiers),
        (train_ratio, validation_ratio, test_ratio),
    )
    if sum(counts) != len(identifiers):
        raise ConfigurationError("Group holdout counts do not cover every group.")
    ordered = list(identifiers)
    # The seed makes the split repeatable. It is not a cryptographic secret.
    generator = random.Random(seed)  # noqa: S311  # nosec B311
    generator.shuffle(ordered)
    train_end = counts[0]
    validation_end = train_end + counts[1]
    return {
        SplitName.TRAIN: tuple(ordered[:train_end]),
        SplitName.VALIDATION: tuple(ordered[train_end:validation_end]),
        SplitName.TEST: tuple(ordered[validation_end:]),
    }


def split_size_risks(
    split: Mapping[SplitName, Sequence[str]],
    *,
    minimum: int = MINIMUM_SPLIT_ASSET_COUNT,
) -> list[dict[str, object]]:
    """Warn when a split is empty or has fewer assets than ``minimum``.

    Args:
        split: Asset ids by split.
        minimum: Smallest asset count that does not raise a risk. Must be
            at least 1.

    Returns:
        One risk mapping per short split, in train, validation, test order.
        The list is empty when every split meets ``minimum``.
    """
    risks: list[dict[str, object]] = []
    for name in (SplitName.TRAIN, SplitName.VALIDATION, SplitName.TEST):
        count = len(split[name])
        if count >= minimum:
            continue
        if count == 0:
            code = "empty_split"
            message = (
                f"Split {name.value} is empty (0 assets), below the minimum of {minimum}. "
                "Metrics for this split are not computed."
            )
        else:
            code = "split_below_minimum"
            message = f"Split {name.value} has {count} assets, below the minimum of {minimum}."
        risks.append(
            {
                "severity": "warning",
                "code": code,
                "split": name.value,
                "asset_count": count,
                "minimum_asset_count": minimum,
                "message": message,
            }
        )
    return risks


def _largest_remainder_counts(
    size: int, ratios: tuple[float, float, float]
) -> tuple[int, int, int]:
    """Turn ratios into integer counts that sum to ``size``.

    Args:
        size: Number of groups.
        ratios: Train, validation, and test shares.

    Returns:
        Three counts in that order.
    """
    raw = [ratio * size for ratio in ratios]
    counts = [int(value) for value in raw]
    leftover = size - sum(counts)
    fractional_order = sorted(
        range(len(ratios)),
        key=lambda index: raw[index] - counts[index],
        reverse=True,
    )
    for index in fractional_order[:leftover]:
        counts[index] += 1
    return counts[0], counts[1], counts[2]
