"""Reference datasets.

v0.1's demo is C-MAPSS FD001. SCANIA Component X is catalogued and refused
until v0.2. Neither dataset is bundled in the wheel.
"""

from rulsafe.datasets.cards import DatasetCard as DatasetCard
from rulsafe.datasets.registry import dataset_card as dataset_card
from rulsafe.datasets.registry import fetch_dataset as fetch_dataset
from rulsafe.datasets.registry import list_datasets as list_datasets

__all__ = [
    "DatasetCard",
    "dataset_card",
    "fetch_dataset",
    "list_datasets",
]
