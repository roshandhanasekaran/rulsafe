"""C-MAPSS FD001, the v0.1 completed-trajectory demo.

Access and licence are separate. The NASA catalog page does not state a
licence. A Zenodo deposit of the same files states CC BY 4.0 for that record
only. Those two statements must not be merged.

Scoring is last-observation only. FD001 on the catalog page is 100 training
engines and 100 test engines.
"""

from rulsafe.datasets.cards import DatasetCard

CMAPSS_FD001 = DatasetCard(
    name="cmapss_fd001",
    available_in="0.1",
    access=(
        "NASA Prognostics Data Repository zip "
        "https://phm-datasets.s3.amazonaws.com/NASA/"
        "6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip "
        "which contains CMAPSSData.zip. The catalog page is "
        "https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data . "
        "FD001 is 100 training engines that run to failure and 100 test engines "
        "that stop before failure. v0.1 scores only the completed training engines."
    ),
    licence=None,
    licence_statement=(
        "Licence: not specified on the NASA catalog page "
        "(https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data)."
    ),
    terms=None,
    citation="Saxena, Goebel, Simon and Eklund, PHM 2008.",
    separate_record_note=(
        "A separate Zenodo deposit (doi:10.5281/zenodo.15346912) states CC BY 4.0 "
        "for that record only. That licence is not the NASA catalog licence."
    ),
    signal_column_count=None,
)
