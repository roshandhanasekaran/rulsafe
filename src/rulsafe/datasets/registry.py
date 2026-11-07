"""Reference dataset catalogue.

Listing a card does not download anything. Fetching is not implemented.
SCANIA is listed so the refusal is explicit: it is a v0.2 dataset.
"""

from pathlib import Path

from rulsafe.datasets.cards import DatasetCard
from rulsafe.datasets.cmapss import CMAPSS_FD001
from rulsafe.datasets.scania_component_x import SCANIA_COMPONENT_X
from rulsafe.exceptions import ConfigurationError, not_implemented

_DATASETS: tuple[DatasetCard, ...] = (CMAPSS_FD001, SCANIA_COMPONENT_X)


def list_datasets() -> tuple[DatasetCard, ...]:
    """Return the known dataset cards, v0.1 demo first.

    Returns:
        C-MAPSS FD001, then SCANIA Component X marked for v0.2.
    """
    return _DATASETS


def dataset_card(dataset_name: str) -> DatasetCard:
    """Return one dataset card.

    Args:
        dataset_name: ``cmapss_fd001`` or ``scania_component_x``.

    Returns:
        The matching card.

    Raises:
        ConfigurationError: The name is not in the catalogue.
    """
    normalized = dataset_name.strip().casefold()
    for card in _DATASETS:
        if card.name == normalized:
            return card
    known = ", ".join(card.name for card in _DATASETS)
    raise ConfigurationError(f"Unknown dataset {dataset_name!r}. Known datasets: {known}.")


def fetch_dataset(dataset_name: str, *, cache_directory: Path | None = None) -> Path:
    """Download a reference dataset after its card has been shown to the caller.

    Args:
        dataset_name: Catalogue name.
        cache_directory: Directory for a local cache. The default later is
            ``~/.cache/rulsafe``.

    Returns:
        Path of the cached dataset.

    Raises:
        ConfigurationError: The name is unknown, or the dataset is not in v0.1.
        NotImplementedError: The v0.1 download itself is not implemented yet.
    """
    card = dataset_card(dataset_name)
    if card.available_in != "0.1":
        raise ConfigurationError(
            f"{card.name} is not part of v0.1 (planned for v{card.available_in}). "
            "v0.1 does not download SCANIA Component X."
        )
    raise not_implemented("fetch_dataset", card.name, cache_directory)
