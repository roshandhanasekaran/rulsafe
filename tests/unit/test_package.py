"""Package metadata and import boundaries."""

import sys
import warnings
from importlib.metadata import version
from pathlib import Path

import pytest

from rulsafe import __version__, run_pipeline
from rulsafe.config import RunConfig
from rulsafe.exceptions import ContractError
from rulsafe.pipeline import execute as execute_module


def test_installed_version_matches_the_package() -> None:
    assert version("rulsafe") == __version__


def test_import_does_not_pull_forbidden_stacks() -> None:
    forbidden = ("sklearn", "streamlit", "autogluon", "sqlalchemy", "psycopg", "snowflake")
    imported = [
        name
        for name in forbidden
        if any(loaded == name or loaded.startswith(f"{name}.") for loaded in sys.modules)
    ]
    assert imported == []


def test_run_pipeline_keeps_the_censored_engine(load_example, tmp_path) -> None:
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    result = run_pipeline(config, output_directory=tmp_path)
    document = result.to_dict()
    censored = document["censored_or_unsupported_asset_ids"]
    assert censored == ["engine_e"]
    assert document["dropped_asset_ids"] == []
    for split_name in ("train", "validation", "test"):
        assert "engine_e" not in document["splits"][split_name]
    entry = _disposition(document, "engine_e")
    assert entry["disposition"] == "report"
    assert entry["used_for_training"] is False
    assert "excluded from every split" in entry["detail"]
    splits = document["splits"]
    assert isinstance(splits, dict)
    for split_name in ("train", "validation", "test"):
        members = splits[split_name]
        assert isinstance(members, list)
        assert members
    test_metrics = document["metrics"]
    assert isinstance(test_metrics, dict)
    held_out = test_metrics["test"]
    assert isinstance(held_out, dict)
    constant_metric = held_out["constant_root_mean_square_error"]
    assert isinstance(constant_metric, dict)
    assert constant_metric["status"] == "COMPUTED"
    assert document["risks"] == []
    assert result.report_paths.json_path is not None
    assert result.report_paths.json_path.is_file()
    copy_path = result.save_json(tmp_path / "copy.json")
    assert copy_path.read_text(encoding="utf-8") == result.report_paths.json_path.read_text(
        encoding="utf-8"
    )


def test_reject_policy_stops_the_run(load_example, tmp_path) -> None:
    raw = load_example("synthetic_panel.yaml")
    labeling = raw["labeling"]
    assert isinstance(labeling, dict)
    raw["labeling"] = {**labeling, "censored_policy": "reject"}
    config = RunConfig.from_mapping(raw)
    with pytest.raises(ContractError, match="reject stopped the run") as caught:
        run_pipeline(config, output_directory=tmp_path)
    assert "engine_e" in str(caught.value)
    assert not (tmp_path / "report.json").exists()


def test_empty_splits_are_warned_and_recorded(load_example, tmp_path) -> None:
    panel = tmp_path / "panel"
    panel.mkdir()
    _write_two_completed_engines(panel)
    raw = load_example("synthetic_panel.yaml")
    connector = raw["connector"]
    assert isinstance(connector, dict)
    raw["connector"] = {
        **connector,
        "assets": str(panel / "assets.csv"),
        "signals": str(panel / "signals.csv"),
        "events": str(panel / "events.csv"),
    }
    config = RunConfig.from_mapping(raw)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        document = run_pipeline(config, output_directory=tmp_path / "run").to_dict()
    messages = [str(item.message) for item in caught if issubclass(item.category, UserWarning)]
    assert any("Split validation is empty" in message for message in messages)
    assert any("Split test is empty" in message for message in messages)
    risks = document["risks"]
    assert isinstance(risks, list)
    empty = [risk for risk in risks if risk["code"] == "empty_split"]
    assert {risk["split"] for risk in empty} == {"validation", "test"}
    assert all(risk["severity"] == "warning" and risk["asset_count"] == 0 for risk in empty)
    held_out = document["metrics"]
    assert isinstance(held_out, dict)
    test_metrics = held_out["test"]
    assert isinstance(test_metrics, dict)
    constant_metric = test_metrics["constant_root_mean_square_error"]
    assert isinstance(constant_metric, dict)
    assert constant_metric["status"] == "NOT_COMPUTED"


def test_a_short_split_is_warned_and_recorded(load_example, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(execute_module, "MINIMUM_SPLIT_ASSET_COUNT", 2)
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        document = run_pipeline(config, output_directory=tmp_path).to_dict()
    messages = [str(item.message) for item in caught if issubclass(item.category, UserWarning)]
    assert any("Split validation has 1 assets" in message for message in messages)
    assert any("below the minimum of 2" in message for message in messages)
    risks = document["risks"]
    assert isinstance(risks, list)
    short = [risk for risk in risks if risk["code"] == "split_below_minimum"]
    assert {risk["split"] for risk in short} == {"validation", "test"}
    assert all(risk["asset_count"] == 1 and risk["minimum_asset_count"] == 2 for risk in short)
    assert all(risk["severity"] == "warning" for risk in short)


def _write_two_completed_engines(directory: Path) -> None:
    (directory / "assets.csv").write_text("asset_id\nengine_a\nengine_b\n", encoding="utf-8")
    (directory / "signals.csv").write_text(
        "asset_id,event_time,available_at,temperature,pressure\n"
        "engine_a,0,0,10,1\n"
        "engine_a,1,1,20,2\n"
        "engine_a,2,2,30,3\n"
        "engine_b,0,0,11,1\n"
        "engine_b,1,1,21,2\n"
        "engine_b,2,2,31,3\n",
        encoding="utf-8",
    )
    (directory / "events.csv").write_text(
        "asset_id,event_time,available_at,event_type,failure_notes\n"
        "engine_a,2,2,failure,bearing\n"
        "engine_b,2,2,failure,bearing\n",
        encoding="utf-8",
    )


def _disposition(document: dict[str, object], asset_id: str) -> dict[str, object]:
    rows = document["history_dispositions"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        if row.get("asset_id") == asset_id:
            return row
    raise AssertionError(f"{asset_id} has no history disposition")
