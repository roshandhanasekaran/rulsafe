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
        "Public NASA Open Data catalog page for the C-MAPSS turbofan degradation "
        "simulation. FD001 is listed as 100 training engines and 100 test engines. "
        "The catalog objective is remaining cycles after the last observed cycle."
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
