"""Steps that turn logical tables into train, validation, and test rows.

The functions in this package are the v0.1 pipeline seams. Most of them
raise ``NotImplementedError`` until a later change fills them in.
``disposition_for_history`` is implemented: censored and unsupported
histories are rejected or reported, never dropped.
"""

from rulsafe.pipeline.episodes import build_episodes as build_episodes
from rulsafe.pipeline.features import build_causal_features as build_causal_features
from rulsafe.pipeline.labels import HistoryDisposition as HistoryDisposition
from rulsafe.pipeline.labels import HistorySupport as HistorySupport
from rulsafe.pipeline.labels import disposition_for_history as disposition_for_history
from rulsafe.pipeline.preprocess import TransformerMembership as TransformerMembership
from rulsafe.pipeline.preprocess import fit_preprocessors as fit_preprocessors
from rulsafe.pipeline.split import assign_splits as assign_splits
from rulsafe.pipeline.windows import build_windows as build_windows

__all__ = [
    "HistoryDisposition",
    "HistorySupport",
    "TransformerMembership",
    "assign_splits",
    "build_causal_features",
    "build_episodes",
    "build_windows",
    "disposition_for_history",
    "fit_preprocessors",
]
