"""Dataset card fields.

Access, licence, and terms are separate. A missing licence stays missing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetCard:
    """How to obtain a reference dataset and what licence to print first.

    Attributes:
        name: Stable identifier used by ``datasets fetch``.
        available_in: Package version that is allowed to fetch it. ``0.2`` means
            v0.1 must refuse the download.
        access: How a person obtains the files, including size when known.
        licence: SPDX identifier when the catalog states one. None when it does not.
        licence_statement: Sentence printed before any download.
        terms: Non-licence terms. None when the source has no separate terms.
        citation: Short citation printed with the dataset.
        separate_record_note: A different deposit's licence. It does not replace
            ``licence``. None when there is nothing to keep separate.
        signal_column_count: Feature columns excluding identifier and time columns.
    """

    name: str
    available_in: str
    access: str
    licence: str | None
    licence_statement: str
    terms: str | None
    citation: str
    separate_record_note: str | None = None
    signal_column_count: int | None = None
