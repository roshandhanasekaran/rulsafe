"""Persistent guards: test rows and future rows do not move the fit."""

import csv
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
import yaml

from rulsafe import load_config, run_pipeline
from rulsafe.config import RunConfig
from rulsafe.contract import GapPolicy
from rulsafe.datasets.synthetic_fleet import CENSORED_ASSET_ID, SENSORS, fleet_tables
from rulsafe.models.baselines import (
    FittedBaseline,
    fit_constant_baseline,
    fit_histogram_gradient_boosting,
)
from rulsafe.pipeline.features import build_causal_features, features_from_windows
from rulsafe.pipeline.windows import build_windows


class _Fits:
    """Training fits observed by one or more pipeline runs."""

    def __init__(self) -> None:
        """Start with no recorded fits."""
        self.constants: list[dict[str, object]] = []
        self.trees: list[dict[str, object]] = []


def test_test_split_changes_do_not_move_the_fit(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Relabelling the test split, or perturbing its features, leaves the fit."""
    fits = _Fits()
    _capture_fits(monkeypatch, fits)
    original = tmp_path / "original"
    _copy_fleet(repository_root, original)
    first = _run(original, tmp_path / "first")
    test_ids = _ids(first, "test")
    relabeled = tmp_path / "relabeled"
    _copy_fleet(repository_root, relabeled)
    _relabel_test(relabeled, test_ids)
    second = _run(relabeled, tmp_path / "second")
    perturbed = tmp_path / "perturbed"
    _copy_fleet(repository_root, perturbed)
    _perturb_test_temperature(perturbed, test_ids)
    third = _run(perturbed, tmp_path / "third")

    assert fits.constants[0] == fits.constants[1] == fits.constants[2]
    assert fits.trees[0] == fits.trees[1] == fits.trees[2]
    assert first["headline_model"] == second["headline_model"] == third["headline_model"]
    assert first["hist_gradient_boosting_iteration_count"] == fits.trees[0]["iteration"]
    assert first["metrics"]["validation"] == second["metrics"]["validation"]
    assert first["metrics"]["validation"] == third["metrics"]["validation"]
    assert _metric(first, "test", "constant_root_mean_square_error") != _metric(
        second, "test", "constant_root_mean_square_error"
    )
    assert _metric(first, "test", "hist_gradient_boosting_root_mean_square_error") != _metric(
        third, "test", "hist_gradient_boosting_root_mean_square_error"
    )


def test_appending_future_rows_does_not_change_earlier_features(
    repository_root: Path, tmp_path: Path
) -> None:
    """A row after time t leaves features at t, and the fit, unchanged."""
    _signals, signals_text, _events = fleet_tables()
    rows = [
        _feature_row(row)
        for row in csv.DictReader(signals_text.splitlines())
        if row["asset_id"] == "unit-01"
    ]
    times = sorted({int(row["event_time"]) for row in rows})
    future = {
        "event_time": times[-1] + 12,
        "available_at": times[-1] + 12,
        "temperature": 999.0,
        "pressure": -50.0,
        "vibration": 80.0,
        "flow": 0.0,
    }
    for prediction_time in times:
        before = build_causal_features(
            rows=rows,
            prediction_time=prediction_time,
            gap_policy=GapPolicy.NONE,
            maximum_gap=None,
            feature_columns=SENSORS,
        )
        after = build_causal_features(
            rows=(*rows, future),
            prediction_time=prediction_time,
            gap_policy=GapPolicy.NONE,
            maximum_gap=None,
            feature_columns=SENSORS,
        )
        assert before == after
        assert _lookback(rows, times) == _lookback((*rows, future), times)

    original = tmp_path / "original"
    extended = tmp_path / "extended"
    _copy_fleet(repository_root, original)
    _copy_fleet(repository_root, extended)
    _append_future_signal(extended, "unit-01")
    first = _run(original, tmp_path / "run-original")
    second = _run(extended, tmp_path / "run-extended")
    assert first["constant_training_value"] == second["constant_training_value"]
    assert first["constant_training_row_count"] == second["constant_training_row_count"]
    assert (
        first["hist_gradient_boosting_iteration_count"]
        == (second["hist_gradient_boosting_iteration_count"])
    )
    assert first["headline_model"] == second["headline_model"]
    assert first["metrics"] == second["metrics"]


def test_fit_rows_come_from_train_assets_only(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fit sees the train assets' prediction rows and no other asset."""
    fits = _Fits()
    _capture_fits(monkeypatch, fits)
    document = _run(repository_root / "examples" / "synthetic_fleet", tmp_path / "run")
    splits = document["splits"]
    assert isinstance(splits, dict)
    train_ids = [str(asset_id) for asset_id in splits["train"]]
    expected = _prediction_row_count(repository_root, train_ids)
    held_out = _prediction_row_count(
        repository_root,
        [str(asset_id) for asset_id in splits["validation"]]
        + [str(asset_id) for asset_id in splits["test"]],
    )
    assert held_out > 0
    assert expected == document["constant_training_row_count"]
    assert expected == document["hist_gradient_boosting_training_row_count"]
    assert fits.constants[0]["count"] == expected
    assert fits.trees[0]["count"] == expected
    assert CENSORED_ASSET_ID not in train_ids
    assert set(train_ids).isdisjoint(splits["validation"])
    assert set(train_ids).isdisjoint(splits["test"])


def _capture_fits(monkeypatch: pytest.MonkeyPatch, fits: _Fits) -> None:
    """Record the training rows and predictions each fit call uses."""

    def spy_constant(*, training_targets: Sequence[float]) -> FittedBaseline:
        fitted = fit_constant_baseline(training_targets=training_targets)
        fits.constants.append(
            {
                "targets": tuple(training_targets),
                "value": fitted.constant_value,
                "count": len(training_targets),
            }
        )
        return fitted

    def spy_tree(
        *,
        training_features: Sequence[Mapping[str, float | None]],
        training_targets: Sequence[float],
        validation_features: Sequence[Mapping[str, float | None]] | None = None,
        validation_targets: Sequence[float] | None = None,
        random_state: int,
    ) -> FittedBaseline:
        fitted = fit_histogram_gradient_boosting(
            training_features=training_features,
            training_targets=training_targets,
            validation_features=validation_features,
            validation_targets=validation_targets,
            random_state=random_state,
        )
        fits.trees.append(
            {
                "targets": tuple(training_targets),
                "features": tuple(tuple(sorted(row.items())) for row in training_features),
                "iteration": fitted.iteration_count,
                "predictions": fitted.predict(training_features),
                "count": len(training_targets),
            }
        )
        return fitted

    monkeypatch.setattr("rulsafe.pipeline.execute.fit_constant_baseline", spy_constant)
    monkeypatch.setattr("rulsafe.pipeline.execute.fit_histogram_gradient_boosting", spy_tree)


def _run(directory: Path, output: Path) -> dict[str, object]:
    """Run the fleet configuration against one CSV directory."""
    loaded = yaml.safe_load(Path("examples/synthetic_fleet.yaml").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    connector = dict(loaded["connector"])
    connector["assets"] = str(directory / "assets.csv")
    connector["signals"] = str(directory / "signals.csv")
    connector["events"] = str(directory / "events.csv")
    loaded["connector"] = connector
    config = RunConfig.from_mapping(loaded)
    assert config.project.name == load_config("examples/synthetic_fleet.yaml").project.name
    return run_pipeline(config, output_directory=output).to_dict()


def _copy_fleet(repository_root: Path, destination: Path) -> None:
    """Copy the committed fleet tables."""
    shutil.copytree(repository_root / "examples" / "synthetic_fleet", destination)


def _ids(document: dict[str, object], split_name: str) -> set[str]:
    """Return the asset ids of one split."""
    splits = document["splits"]
    assert isinstance(splits, dict)
    members = splits[split_name]
    assert isinstance(members, list)
    return {str(asset_id) for asset_id in members}


def _relabel_test(directory: Path, test_ids: set[str]) -> None:
    """Move each test failure five cycles later without adding signal rows."""
    fields, rows = _read_csv(directory / "events.csv")
    for row in rows:
        if row["asset_id"] in test_ids and row["event_type"] == "failure":
            moved = int(row["event_time"]) + 5
            row["event_time"] = str(moved)
            row["available_at"] = str(moved)
    _write_csv(directory / "events.csv", fields, rows)


def _perturb_test_temperature(directory: Path, test_ids: set[str]) -> None:
    """Add a large offset to test-asset temperature only."""
    fields, rows = _read_csv(directory / "signals.csv")
    for row in rows:
        if row["asset_id"] in test_ids:
            row["temperature"] = f"{float(row['temperature']) + 50.0:.4f}"
    _write_csv(directory / "signals.csv", fields, rows)


def _append_future_signal(directory: Path, asset_id: str) -> None:
    """Append one signal row after that asset's failure."""
    _fields, events = _read_csv(directory / "events.csv")
    failure = next(
        int(row["event_time"])
        for row in events
        if row["asset_id"] == asset_id and row["event_type"] == "failure"
    )
    fields, rows = _read_csv(directory / "signals.csv")
    extra = dict.fromkeys(fields, "")
    extra.update(
        {
            "asset_id": asset_id,
            "event_time": str(failure + 8),
            "available_at": str(failure + 8),
            "temperature": "999.0000",
            "pressure": "-50.0000",
            "vibration": "80.0000",
            "flow": "0.0000",
        }
    )
    rows.append(extra)
    _write_csv(directory / "signals.csv", fields, rows)


def _prediction_row_count(repository_root: Path, asset_ids: list[str]) -> int:
    """Count signal times strictly before each asset's failure."""
    allowed = set(asset_ids)
    events = _read_csv(repository_root / "examples" / "synthetic_fleet" / "events.csv")[1]
    failures = {
        row["asset_id"]: int(row["event_time"])
        for row in events
        if row["event_type"] == "failure" and row["asset_id"] in allowed
    }
    signals = _read_csv(repository_root / "examples" / "synthetic_fleet" / "signals.csv")[1]
    seen: set[tuple[str, int]] = set()
    for row in signals:
        asset_id = row["asset_id"]
        if asset_id not in failures:
            continue
        cycle = int(row["event_time"])
        if cycle < failures[asset_id]:
            seen.add((asset_id, cycle))
    return len(seen)


def _lookback(
    rows: Sequence[Mapping[str, object]], times: Sequence[int]
) -> list[dict[str, float | None]]:
    """Build causal lookback features at the given times."""
    windows = build_windows(
        rows=rows,
        lookback=16,
        stride=1,
        discard_straddle_split=True,
        prediction_times=times,
        gap_policy=GapPolicy.NONE,
        maximum_gap=None,
    )
    return features_from_windows(windows, SENSORS)


def _feature_row(row: dict[str, str]) -> dict[str, object]:
    """Convert one fleet signal row to the feature builder's names."""
    converted: dict[str, object] = {
        "event_time": int(row["event_time"]),
        "available_at": int(row["available_at"]),
    }
    for name in SENSORS:
        converted[name] = float(row[name])
    return converted


def _metric(document: dict[str, object], split_name: str, metric_name: str) -> float:
    """Return one computed metric value."""
    metrics = document["metrics"]
    assert isinstance(metrics, dict)
    block = metrics[split_name]
    assert isinstance(block, dict)
    metric = block[metric_name]
    assert isinstance(metric, dict)
    value = metric["value"]
    assert isinstance(value, float)
    return value


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV file as strings."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        return fields, list(reader)


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    """Write a CSV file with a trailing newline."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
