"""Causal lookback windows and the train-only clip and scaler."""

import pytest

from rulsafe.config import ScalerName
from rulsafe.contract import GapPolicy
from rulsafe.exceptions import ConfigurationError, ContractError
from rulsafe.pipeline.features import features_from_windows, lookback_feature_names
from rulsafe.pipeline.preprocess import fit_preprocessors
from rulsafe.pipeline.windows import build_windows


def _row(
    event_time: float,
    available_at: float,
    temperature: float | None,
    *,
    split: str | None = None,
) -> dict[str, object]:
    """Build one signal row for a window test."""
    row: dict[str, object] = {
        "event_time": event_time,
        "available_at": available_at,
        "temperature": "" if temperature is None else temperature,
    }
    if split is not None:
        row["split"] = split
    return row


def test_lookback_uses_only_past_rows_and_computes_slope() -> None:
    """A future row and a delayed row stay out. Slope follows the past line."""
    rows = (
        _row(0, 0, 0),
        _row(1, 1, 1),
        _row(2, 2, 2),
        _row(0, 5, 99),
        _row(9, 9, 50),
    )
    windows = build_windows(
        rows=rows,
        lookback=3,
        stride=1,
        discard_straddle_split=True,
        prediction_times=(2,),
        gap_policy=GapPolicy.NONE,
        maximum_gap=None,
    )
    assert [row["event_time"] for row in windows[0]["rows"]] == [0, 1, 2]
    features = features_from_windows(windows, ("temperature",))[0]
    assert features["temperature"] == 2
    assert features["temperature_mean"] == pytest.approx(1)
    assert features["temperature_slope"] == pytest.approx(1)
    early = build_windows(
        rows=rows,
        lookback=4,
        stride=1,
        discard_straddle_split=False,
        prediction_times=(0,),
    )
    early_values = [row["temperature"] for row in early[0]["rows"]]
    assert 99 not in early_values
    assert 50 not in early_values
    released = build_windows(
        rows=rows,
        lookback=8,
        stride=1,
        discard_straddle_split=False,
        prediction_times=(2, 5),
    )
    assert 99 not in [row["temperature"] for row in released[0]["rows"]]
    assert 99 in [row["temperature"] for row in released[1]["rows"]]
    assert 50 not in [row["temperature"] for row in released[1]["rows"]]


def test_forward_fill_gap_and_straddle_windows_are_honoured() -> None:
    """Old rows fall outside max_gap, and a mixed split window is dropped."""
    aged = build_windows(
        rows=(_row(0, 0, 1), _row(5, 5, 2)),
        lookback=4,
        stride=1,
        discard_straddle_split=False,
        prediction_times=(5,),
        gap_policy=GapPolicy.FORWARD_FILL,
        maximum_gap=1,
    )
    assert [row["event_time"] for row in aged[0]["rows"]] == [5]
    mixed = build_windows(
        rows=(_row(0, 0, 1, split="train"), _row(1, 1, 2, split="test")),
        lookback=2,
        stride=1,
        discard_straddle_split=True,
        prediction_times=(1,),
    )
    assert mixed == ()
    kept = build_windows(
        rows=(_row(0, 0, 1, split="train"), _row(1, 1, 2, split="test")),
        lookback=2,
        stride=1,
        discard_straddle_split=False,
        prediction_times=(1,),
    )
    assert len(kept) == 1


def test_stride_keeps_every_nth_time_and_bad_settings_are_rejected() -> None:
    """Stride 2 drops the middle time. Lookback below 1 is an error."""
    windows = build_windows(
        rows=(_row(0, 0, 1), _row(1, 1, 2), _row(2, 2, 3)),
        lookback=1,
        stride=2,
        discard_straddle_split=False,
    )
    assert [window["prediction_time"] for window in windows] == [0, 2]
    with pytest.raises(ConfigurationError, match="lookback"):
        build_windows(rows=(), lookback=0, stride=1, discard_straddle_split=False)
    with pytest.raises(ConfigurationError, match="stride"):
        build_windows(rows=(), lookback=1, stride=0, discard_straddle_split=False)
    with pytest.raises(ConfigurationError, match="max_gap"):
        build_windows(
            rows=(_row(0, 0, 1),),
            lookback=1,
            stride=1,
            discard_straddle_split=False,
            gap_policy=GapPolicy.FORWARD_FILL,
            maximum_gap=None,
        )
    with pytest.raises(ConfigurationError, match="missing event_time"):
        build_windows(
            rows=({"available_at": 0, "temperature": 1},),
            lookback=1,
            stride=1,
            discard_straddle_split=False,
        )
    with pytest.raises(ConfigurationError, match="missing its rows"):
        features_from_windows(({"prediction_time": 0},), ("temperature",))
    with pytest.raises(ConfigurationError, match="collides"):
        lookback_feature_names(("temperature", "temperature_mean"))


def test_standard_scaler_and_clip_are_fit_on_train_rows_only() -> None:
    """An extreme held-out value does not move the training clip or center."""
    training = (
        {"temperature": 0.0},
        {"temperature": 10.0},
        {"temperature": 10.0},
        {"temperature": 10.0},
    )
    fitted = fit_preprocessors(
        training,
        asset_ids=("a", "a", "b", "b"),
        feature_names=("temperature",),
        clip_percentiles=(0.0, 100.0),
        scaler=ScalerName.STANDARD,
    )
    assert fitted.membership.split_name == "train"
    assert fitted.membership.fitted_row_count == 4
    transformed = [fitted.transform(row)["temperature"] for row in training]
    assert sum(value for value in transformed if value is not None) == pytest.approx(0.0)
    clipped = fit_preprocessors(
        ({"temperature": 0.0}, {"temperature": 100.0}),
        asset_ids=("a", "a"),
        feature_names=("temperature",),
        clip_percentiles=(50.0, 50.0),
        scaler=ScalerName.STANDARD,
    )
    assert clipped.transform({"temperature": 1000.0})["temperature"] == pytest.approx(0.0)
    unchanged = fit_preprocessors(
        training,
        asset_ids=("a", "a", "b", "b"),
        feature_names=("temperature",),
        clip_percentiles=(0.0, 100.0),
        scaler=ScalerName.STANDARD,
    )
    assert unchanged.clip_high["temperature"] == fitted.clip_high["temperature"]
    identity = fit_preprocessors(
        training,
        asset_ids=("a", "a", "b", "b"),
        feature_names=("temperature",),
        clip_percentiles=(0.0, 100.0),
        scaler=ScalerName.NONE,
    )
    assert identity.transform({"temperature": 10.0})["temperature"] == pytest.approx(10.0)
    scaled = fit_preprocessors(
        ({"temperature": 0.0}, {"temperature": 10.0}),
        asset_ids=("a", "b"),
        feature_names=("temperature",),
        clip_percentiles=(0.0, 100.0),
        scaler=ScalerName.MINMAX,
    )
    assert scaled.transform({"temperature": 10.0})["temperature"] == pytest.approx(1.0)
    assert scaled.transform({"temperature": None})["temperature"] is None
    with pytest.raises(ContractError, match="at least one"):
        fit_preprocessors(
            (),
            asset_ids=(),
            feature_names=("temperature",),
            clip_percentiles=(1.0, 99.0),
            scaler=ScalerName.STANDARD,
        )
    with pytest.raises(ContractError, match="same length"):
        fit_preprocessors(
            training,
            asset_ids=("a",),
            feature_names=("temperature",),
            clip_percentiles=(0.0, 100.0),
            scaler=ScalerName.STANDARD,
        )
    blank = fit_preprocessors(
        ({"temperature": None},),
        asset_ids=("a",),
        feature_names=("temperature",),
        clip_percentiles=(1.0, 99.0),
        scaler=ScalerName.STANDARD,
    )
    assert blank.transform({"temperature": 4.0})["temperature"] == pytest.approx(0.0)
    flat = fit_preprocessors(
        ({"temperature": 3.0}, {"temperature": 3.0}),
        asset_ids=("a", "b"),
        feature_names=("temperature",),
        clip_percentiles=(0.0, 100.0),
        scaler=ScalerName.MINMAX,
    )
    assert flat.transform({"temperature": 3.0})["temperature"] == pytest.approx(0.0)
