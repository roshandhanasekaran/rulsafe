"""SCANIA Component X is a v0.2 fleet dataset.

v0.1 does not download it and does not treat it as the demo. The access and
licence facts below are kept so a later adapter does not have to rediscover
them. The catalogue licence is CC BY 4.0 and is not re-licensed as Apache-2.0.
Operational readouts have 105 signal columns plus ``vehicle_id`` and ``time_step``.
"""

from rulsafe.datasets.cards import DatasetCard

SCANIA_COMPONENT_X = DatasetCard(
    name="scania_component_x",
    available_in="0.2",
    access=(
        "Openly accessible on the researchdata.se catalogue entry 2024-34: "
        "11 files, 1.54 GiB. Version 3, DOI 10.5878/bnh5-ka77, published 2025-04-09."
    ),
    licence="CC-BY-4.0",
    licence_statement="Licence: Creative Commons Attribution 4.0 International (CC BY 4.0).",
    terms=None,
    citation=(
        "Kharazian, Lindgren, Magnússon, Steinert and Andersson Reyna, "
        "Scientific Data 12, 493 (2025). doi:10.1038/s41597-025-04802-6."
    ),
    separate_record_note=None,
    signal_column_count=105,
)
