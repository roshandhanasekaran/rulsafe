"""The synthetic demo fleet is noisy, varied, and larger than the smoke panel."""

import csv
import warnings
from io import StringIO
from pathlib import Path

from rulsafe import load_config, run_pipeline
from rulsafe.datasets.synthetic_fleet import (
    CENSORED_ASSET_ID,
    COMPLETED_ASSET_COUNT,
    SENSORS,
    completed_asset_id,
    fleet_tables,
    lifetime_cycles,
    write_fleet,
)


def test_committed_fleet_matches_the_generator(repository_root: Path, tmp_path: Path) -> None:
    """The demo files are the deterministic generator output."""
    assets, signals, events = fleet_tables()
    directory = repository_root / "examples" / "synthetic_fleet"
    assert (directory / "assets.csv").read_text(encoding="utf-8") == assets
    assert (directory / "signals.csv").read_text(encoding="utf-8") == signals
    assert (directory / "events.csv").read_text(encoding="utf-8") == events
    assert fleet_tables() == (assets, signals, events)
    write_fleet(tmp_path)
    assert (tmp_path / "assets.csv").read_text(encoding="utf-8") == assets
    assert (tmp_path / "signals.csv").read_text(encoding="utf-8") == signals
    assert (tmp_path / "events.csv").read_text(encoding="utf-8") == events


def test_lifetimes_and_sensors_are_not_a_single_rul_line() -> None:
    """Remaining life is not `3 - pressure`, and the sensors drift and differ."""
    lifetimes = [lifetime_cycles(index) for index in range(1, COMPLETED_ASSET_COUNT + 1)]
    assert len(set(lifetimes)) >= 8
    assert min(lifetimes) != max(lifetimes)
    _, signals_text, events_text = fleet_tables()
    signals = list(csv.DictReader(StringIO(signals_text)))
    failures = {
        row["asset_id"]: int(row["event_time"])
        for row in csv.DictReader(StringIO(events_text))
        if row["event_type"] == "failure"
    }
    assert len(failures) == COMPLETED_ASSET_COUNT
    pairs: list[tuple[float, float]] = []
    starts: list[float] = []
    ends: list[float] = []
    for row in signals:
        asset_id = row["asset_id"]
        if asset_id not in failures:
            continue
        cycle = int(row["event_time"])
        if cycle == 0:
            starts.append(float(row["temperature"]))
        if cycle >= failures[asset_id]:
            continue
        if cycle == failures[asset_id] - 1:
            ends.append(float(row["temperature"]))
        pairs.append((float(row["pressure"]), float(failures[asset_id] - cycle)))
    assert len(set(SENSORS)) >= 4
    assert len(set(starts)) > 1
    assert sum(ends) / len(ends) > sum(starts) / len(starts)
    assert _max_linear_residual(pairs) > 0.5
    assert any(abs(rul - (3.0 - pressure)) > 0.5 for pressure, rul in pairs)


def test_demo_fleet_has_three_assets_in_every_split(repository_root: Path, tmp_path: Path) -> None:
    """The demo split is large enough that the small-split warning stays quiet."""
    config = load_config(repository_root / "examples" / "synthetic_fleet.yaml")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        document = run_pipeline(config, output_directory=tmp_path).to_dict()
    assert caught == []
    splits = document["splits"]
    assert isinstance(splits, dict)
    for split_name in ("train", "validation", "test"):
        members = splits[split_name]
        assert isinstance(members, list)
        assert len(members) >= 3
    assert document["censored_or_unsupported_asset_ids"] == [CENSORED_ASSET_ID]
    assert CENSORED_ASSET_ID not in splits["train"] + splits["validation"] + splits["test"]
    assert document["risks"] == []
    assert document["headline_split"] == "test"
    assert completed_asset_id(1) in splits["train"] + splits["validation"] + splits["test"]


def _max_linear_residual(pairs: list[tuple[float, float]]) -> float:
    """Return the largest absolute residual of a one-variable line."""
    count = len(pairs)
    mean_x = sum(x_value for x_value, _ in pairs) / count
    mean_y = sum(y_value for _, y_value in pairs) / count
    variance = sum((x_value - mean_x) ** 2 for x_value, _ in pairs)
    covariance = sum((x_value - mean_x) * (y_value - mean_y) for x_value, y_value in pairs)
    slope = covariance / variance
    intercept = mean_y - slope * mean_x
    return max(abs(y_value - (intercept + slope * x_value)) for x_value, y_value in pairs)
