"""Train, validation, and final-test splits.

``random`` is not a protocol. ``global_time`` is deferred to v0.2.
``group_holdout`` assigns each asset to one split. Early stopping and model
selection use validation. The headline evaluation is the final test, scored
once after that choice is frozen.
"""

import random
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path

from rulsafe.config import DEFAULT_MIN_ASSETS_PER_SPLIT, SplitProtocol
from rulsafe.exceptions import ConfigurationError, not_implemented

# Kept as the name callers already use. The value is the configured default:
# validation and test splits smaller than this are warnings in the report.
MINIMUM_SPLIT_ASSET_COUNT = DEFAULT_MIN_ASSETS_PER_SPLIT


class SplitName(StrEnum):
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
        protocol: ``group_holdout``. Official files are handled by
            :func:`assign_official_partitions`.
        group_identifiers: Asset or group ids. Duplicates are ignored.
        train_ratio: Share of groups for train.
        validation_ratio: Share of groups for validation.
        test_ratio: Share of groups for the final test.
        seed: Shuffle seed. The same seed and ids always give the same split.

    Returns:
        Entity identifiers by split. Each id appears in one split.

    Raises:
        NotImplementedError: The protocol is not ``group_holdout``; use
            :func:`assign_official_partitions` for official files.
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


def read_split_ids(path: Path) -> tuple[str, ...]:
    """Read one asset id per line.

    Args:
        path: Text file of asset ids.

    Returns:
        Ids in file order, with blank lines ignored.

    Raises:
        ConfigurationError: The file is missing, empty, or repeats an id.
    """
    if not path.is_file():
        raise ConfigurationError(f"Could not read split id file {path}.")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(f"Could not read split id file {path}.") from error
    identifiers = tuple(line.strip() for line in text.splitlines() if line.strip())
    if not identifiers:
        raise ConfigurationError(f"Split id file {path} has no asset ids.")
    if len(identifiers) != len(set(identifiers)):
        raise ConfigurationError(f"Split id file {path} repeats an asset id.")
    return identifiers


def assign_official_partitions(
    group_identifiers: Sequence[str],
    *,
    train_ids: Sequence[str],
    validation_ids: Sequence[str],
    test_ids: Sequence[str],
) -> dict[SplitName, tuple[str, ...]]:
    """Place each completed asset on the official id-file split.

    The files are not shuffled. An asset that is not in exactly one file is
    an error. Censored assets are not passed in ``group_identifiers``; an id
    file that names one of them fails because that id is not a scored asset.

    Args:
        group_identifiers: Completed asset ids that must be placed.
        train_ids: Train ids in file order.
        validation_ids: Validation ids in file order.
        test_ids: Final-test ids in file order.

    Returns:
        Asset ids by split, in the id-file order.

    Raises:
        ConfigurationError: The files overlap, or they are not exactly the
            completed assets.
    """
    groups = tuple(dict.fromkeys(group_identifiers))
    listed = (tuple(train_ids), tuple(validation_ids), tuple(test_ids))
    combined = listed[0] + listed[1] + listed[2]
    if len(combined) != len(set(combined)):
        raise ConfigurationError("An asset id is in more than one official partition.")
    missing = sorted(set(groups) - set(combined))
    extra = sorted(set(combined) - set(groups))
    if missing or extra:
        raise ConfigurationError(
            "Official partition files must list each completed asset once and "
            f"no other asset. Missing: {missing or 'none'}. Extra: {extra or 'none'}."
        )
    return {
        SplitName.TRAIN: listed[0],
        SplitName.VALIDATION: listed[1],
        SplitName.TEST: listed[2],
    }


def partition_in_given_order(
    identifiers: Sequence[str],
    ratios: tuple[float, float, float] = (0.70, 0.15, 0.15),
) -> dict[SplitName, tuple[str, ...]]:
    """Assign ids in the order given, without shuffling.

    Args:
        identifiers: Asset ids already sorted by the caller.
        ratios: Train, validation, and test shares.

    Returns:
        The three splits in that order.

    Raises:
        ConfigurationError: A share would receive no assets.
    """
    counts = _largest_remainder_counts(len(identifiers), ratios)
    if any(count == 0 for count in counts):
        raise ConfigurationError(
            "The completed-trajectory partition needs at least one asset in "
            f"train, validation, and test. Counts were {counts}."
        )
    train_end = counts[0]
    validation_end = train_end + counts[1]
    ordered = tuple(identifiers)
    return {
        SplitName.TRAIN: ordered[:train_end],
        SplitName.VALIDATION: ordered[train_end:validation_end],
        SplitName.TEST: ordered[validation_end:],
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
                "Root mean square error, mean absolute error, and the NASA score "
                "for this split are NOT_COMPUTED."
            )
        else:
            code = "split_below_minimum"
            asset_word = "asset" if count == 1 else "assets"
            message = (
                f"Split {name.value} has {count} {asset_word}, below the minimum of {minimum}. "
                "Scores for this split are still reported."
            )
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
