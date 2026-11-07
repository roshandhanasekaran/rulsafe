"""Property tests for label disposition and split acceptance."""

import copy
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from rulsafe.config import CensoredHistoryPolicy, RunConfig
from rulsafe.exceptions import ConfigurationError
from rulsafe.pipeline.labels import HistoryDisposition, HistorySupport, disposition_for_history

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

_ALLOWED_DISPOSITIONS = frozenset(HistoryDisposition)


def _example(name: str) -> dict[str, object]:
    """Load one example configuration as a mutable mapping.

    Args:
        name: File name under ``examples/``.

    Returns:
        The parsed YAML mapping.
    """
    import yaml

    loaded = yaml.safe_load((_EXAMPLES / name).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError(f"{name} is not a mapping")
    document: dict[str, object] = {}
    for key, value in loaded.items():
        if not isinstance(key, str):
            raise AssertionError("example keys must be strings")
        document[key] = value
    return document


@given(
    support=st.sampled_from(HistorySupport),
    policy=st.sampled_from(CensoredHistoryPolicy),
)
@settings(max_examples=50)
def test_disposition_never_drops_a_history(
    support: HistorySupport,
    policy: CensoredHistoryPolicy,
) -> None:
    """Every history gets an explicit disposition, never a silent drop."""
    disposition = disposition_for_history(support, policy)
    assert disposition in _ALLOWED_DISPOSITIONS
    assert "drop" not in disposition.value
    if support is HistorySupport.COMPLETED:
        assert disposition is HistoryDisposition.TRAIN
    elif support is HistorySupport.OFFICIAL_LAST_OBSERVATION:
        assert disposition is HistoryDisposition.SCORE_LAST_OBSERVATION
    else:
        assert disposition in {HistoryDisposition.REJECT, HistoryDisposition.REPORT}
        if policy is CensoredHistoryPolicy.REJECT:
            assert disposition is HistoryDisposition.REJECT
        else:
            assert disposition is HistoryDisposition.REPORT


@given(protocol=st.sampled_from(["global_time", "GLOBAL_TIME", "Global_Time", " global_time "]))
@settings(max_examples=20)
def test_global_time_spellings_are_deferred(protocol: str) -> None:
    """Any spelling of global_time is rejected as a v0.2 feature."""
    document = copy.deepcopy(_example("synthetic_panel.yaml"))
    document["split"] = {"protocol": protocol}
    with pytest.raises(ConfigurationError, match=r"deferred to v0\.2"):
        RunConfig.from_mapping(document)


@given(
    train_ratio=st.floats(min_value=0.05, max_value=0.8),
    validation_ratio=st.floats(min_value=0.05, max_value=0.8),
)
@settings(max_examples=30)
def test_group_holdout_accepts_only_ratios_that_sum_to_one(
    train_ratio: float,
    validation_ratio: float,
) -> None:
    """A group holdout is valid only when the three ratios are positive and sum to one."""
    test_ratio = 1.0 - train_ratio - validation_ratio
    document = copy.deepcopy(_example("synthetic_panel.yaml"))
    split = document["split"]
    assert isinstance(split, dict)
    holdout = split["group_holdout"]
    assert isinstance(holdout, dict)
    holdout["train_ratio"] = train_ratio
    holdout["validation_ratio"] = validation_ratio
    holdout["test_ratio"] = test_ratio
    if 0.0 < test_ratio < 1.0:
        loaded = RunConfig.from_mapping(document)
        assert loaded.split.protocol.value == "group_holdout"
    else:
        with pytest.raises(ConfigurationError):
            RunConfig.from_mapping(document)
