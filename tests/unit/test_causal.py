"""Causal features ignore rows that are not yet knowable."""

from pathlib import Path

import pytest

from rulsafe.config import BaselineName, SplitProtocol
from rulsafe.contract import GapPolicy
from rulsafe.exceptions import ConfigurationError
from rulsafe.models.baselines import fit_constant_baseline
from rulsafe.pipeline.features import build_causal_features
from rulsafe.pipeline.split import SplitName, assign_splits, split_size_risks


def test_future_rows_do_not_change_earlier_features() -> None:
    rows = (
        {"event_time": 0, "available_at": 0, "temperature": 10},
        {"event_time": 1, "available_at": 1, "temperature": 20},
    )
    before = build_causal_features(
        rows=rows,
        prediction_time=0,
        gap_policy=GapPolicy.NONE,
        maximum_gap=None,
        feature_columns=("temperature",),
    )
    after = build_causal_features(
        rows=(*rows, {"event_time": 5, "available_at": 5, "temperature": 99}),
        prediction_time=0,
        gap_policy=GapPolicy.NONE,
        maximum_gap=None,
        feature_columns=("temperature",),
    )
    assert before == after
    assert before["temperature"] == 10.0


def test_delayed_record_is_hidden_until_it_is_knowable() -> None:
    rows = (
        {"event_time": 0, "available_at": 0, "temperature": 10},
        {"event_time": 0, "available_at": 5, "temperature": 99},
    )
    at_zero = build_causal_features(
        rows=rows,
        prediction_time=0,
        gap_policy=GapPolicy.NONE,
        maximum_gap=None,
        feature_columns=("temperature",),
    )
    at_five = build_causal_features(
        rows=rows,
        prediction_time=5,
        gap_policy=GapPolicy.NONE,
        maximum_gap=None,
        feature_columns=("temperature",),
    )
    assert at_zero["temperature"] == 10.0
    assert at_five["temperature"] == 99.0


def test_constant_baseline_uses_only_the_training_targets() -> None:
    fitted = fit_constant_baseline(training_targets=(1.0, 3.0))
    assert fitted.name is BaselineName.CONSTANT
    assert fitted.constant_value == 2.0
    assert fitted.training_row_count == 2


def test_forward_fill_ignores_values_older_than_the_gap() -> None:
    rows = (
        {"event_time": 0, "available_at": 0, "temperature": 10},
        {"event_time": 1, "available_at": 1, "temperature": 20},
    )
    filled = build_causal_features(
        rows=rows,
        prediction_time=4,
        gap_policy=GapPolicy.FORWARD_FILL,
        maximum_gap=2,
        feature_columns=("temperature",),
    )
    assert filled["temperature"] is None


def test_rejected_history_is_not_scored() -> None:
    from rulsafe.config import CensoredHistoryPolicy
    from rulsafe.exceptions import ContractError
    from rulsafe.pipeline.labels import HistorySupport, assign_remaining_life

    with pytest.raises(ContractError, match="not dropped silently"):
        assign_remaining_life(
            support=HistorySupport.CENSORED,
            policy=CensoredHistoryPolicy.REJECT,
            prediction_time=0,
            episode_end=1,
        )


def test_forward_fill_requires_a_maximum_gap() -> None:
    with pytest.raises(ConfigurationError, match="max_gap"):
        build_causal_features(
            rows=({"event_time": 0, "available_at": 0, "temperature": 1},),
            prediction_time=0,
            gap_policy=GapPolicy.FORWARD_FILL,
            maximum_gap=None,
            feature_columns=("temperature",),
        )


def test_scored_history_returns_remaining_life() -> None:
    from rulsafe.config import CensoredHistoryPolicy
    from rulsafe.exceptions import ContractError
    from rulsafe.pipeline.labels import HistorySupport, assign_remaining_life

    remaining = assign_remaining_life(
        support=HistorySupport.COMPLETED,
        policy=CensoredHistoryPolicy.REPORT,
        prediction_time=1,
        episode_end=4,
    )
    assert remaining == 3
    with pytest.raises(ContractError, match="earlier"):
        assign_remaining_life(
            support=HistorySupport.COMPLETED,
            policy=CensoredHistoryPolicy.REPORT,
            prediction_time=5,
            episode_end=4,
        )


def test_constant_baseline_rejects_an_empty_training_split() -> None:
    from rulsafe.exceptions import ContractError

    with pytest.raises(ContractError, match="training target"):
        fit_constant_baseline(training_targets=())


def test_missing_csv_is_rejected(tmp_path: Path) -> None:
    from rulsafe.contract import LogicalTableRole
    from rulsafe.io.files import load_table

    missing = tmp_path / "missing.csv"
    with pytest.raises(ConfigurationError, match="Could not read"):
        load_table(missing, LogicalTableRole.SIGNALS)
    empty = tmp_path / "empty.csv"
    empty.write_text("asset_id\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="no data rows"):
        load_table(empty, LogicalTableRole.SIGNALS)


def test_split_size_risks_name_an_empty_split_and_a_short_split() -> None:
    empty = split_size_risks(
        {
            SplitName.TRAIN: ("engine_a",),
            SplitName.VALIDATION: (),
            SplitName.TEST: (),
        },
        minimum=1,
    )
    assert [risk["code"] for risk in empty] == ["empty_split", "empty_split"]
    assert empty[0]["split"] == "validation"
    assert empty[0]["severity"] == "warning"
    assert "empty" in str(empty[0]["message"])
    assert "NOT_COMPUTED" in str(empty[0]["message"])
    assert empty[0]["asset_count"] == 0

    short = split_size_risks(
        {
            SplitName.TRAIN: ("engine_a", "engine_b"),
            SplitName.VALIDATION: ("engine_c",),
            SplitName.TEST: ("engine_d", "engine_e"),
        },
        minimum=2,
    )
    assert [risk["code"] for risk in short] == ["split_below_minimum"]
    assert short[0]["split"] == "validation"
    assert short[0]["asset_count"] == 1
    assert short[0]["minimum_asset_count"] == 2
    assert (
        split_size_risks(
            {
                SplitName.TRAIN: ("engine_a",),
                SplitName.VALIDATION: ("engine_b",),
                SplitName.TEST: ("engine_c",),
            },
            minimum=1,
        )
        == []
    )


def test_group_holdout_puts_each_asset_in_one_split() -> None:
    split = assign_splits(
        SplitProtocol.GROUP_HOLDOUT,
        group_identifiers=("engine_a", "engine_b", "engine_c", "engine_d", "engine_e"),
        train_ratio=0.70,
        validation_ratio=0.15,
        test_ratio=0.15,
        seed=7,
    )
    combined = split[SplitName.TRAIN] + split[SplitName.VALIDATION] + split[SplitName.TEST]
    assert sorted(combined) == ["engine_a", "engine_b", "engine_c", "engine_d", "engine_e"]
    assert len(combined) == len(set(combined))
