"""Package metadata and import boundaries."""

import json
import subprocess
import sys
import warnings
from importlib.metadata import version
from pathlib import Path

import pytest

from rulsafe import __version__, run_pipeline
from rulsafe.config import RunConfig
from rulsafe.exceptions import ContractError


def test_installed_version_matches_the_package() -> None:
    assert version("rulsafe") == __version__


def test_import_does_not_pull_forbidden_stacks() -> None:
    script = (
        "import sys\n"
        "import rulsafe\n"
        "forbidden = ('sklearn', 'streamlit', 'autogluon', 'sqlalchemy', 'psycopg', 'snowflake')\n"
        "imported = [\n"
        "    name for name in forbidden\n"
        "    if any(loaded == name or loaded.startswith(name + '.') for loaded in sys.modules)\n"
        "]\n"
        "raise SystemExit(0 if imported == [] else 1)\n"
    )
    completed = subprocess.run([sys.executable, "-c", script], check=False)  # noqa: S603
    assert completed.returncode == 0


def test_run_pipeline_keeps_the_censored_engine(load_example, tmp_path) -> None:
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
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
    assert document["status"] == "COMPLETED"
    assert document["min_assets_per_split"] == 3
    splits = document["splits"]
    assert isinstance(splits, dict)
    for split_name in ("train", "validation", "test"):
        members = splits[split_name]
        assert isinstance(members, list)
        assert members
    assert document["contract_violations"] == []
    _assert_computed_model_metrics(document["metrics"])
    risks = document["risks"]
    assert isinstance(risks, list)
    warned = {risk["split"] for risk in risks if risk["code"] == "split_below_minimum"}
    assert warned == {"validation", "test"}
    assert all(risk["asset_count"] == 1 and risk["minimum_asset_count"] == 3 for risk in risks)
    assert document["hist_gradient_boosting_early_stopping_split"] == "validation"
    assert document["tree_model_status"] == "COMPUTED"
    assert "NASA score is reported and is not a gate" in str(document["headline_criterion"])
    _assert_headline_follows_validation_rmse(document)
    assert result.report_paths.json_path is not None
    assert result.report_paths.json_path.is_file()
    copy_path = result.save_json(tmp_path / "copy.json")
    assert copy_path.read_text(encoding="utf-8") == result.report_paths.json_path.read_text(
        encoding="utf-8"
    )


def test_reject_policy_writes_a_failed_report_then_stops(load_example, tmp_path) -> None:
    raw = load_example("synthetic_panel.yaml")
    labeling = raw["labeling"]
    assert isinstance(labeling, dict)
    raw["labeling"] = {**labeling, "censored_policy": "reject"}
    config = RunConfig.from_mapping(raw)
    with pytest.raises(ContractError, match="reject stopped the run") as caught:
        run_pipeline(config, output_directory=tmp_path)
    assert "engine_e" in str(caught.value)
    assert "FAILED" in str(caught.value)
    report_path = tmp_path / "report.json"
    assert report_path.is_file()
    document = json.loads(report_path.read_text(encoding="utf-8"))
    assert document["status"] == "FAILED"
    assert document["metrics"] is None
    assert document["splits"] is None
    assert document["headline_model"] is None
    violations = document["contract_violations"]
    assert isinstance(violations, list)
    assert violations[0]["asset_id"] == "engine_e"
    assert violations[0]["disposition"] == "reject"
    assert "constant_root_mean_square_error" not in report_path.read_text(encoding="utf-8")


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
    tree_metric = test_metrics["hist_gradient_boosting_root_mean_square_error"]
    assert isinstance(tree_metric, dict)
    assert tree_metric["status"] == "NOT_COMPUTED"
    assert all("NOT_COMPUTED" in str(risk["message"]) for risk in empty)


def test_min_assets_per_split_can_be_lowered(load_example, tmp_path) -> None:
    raw = load_example("synthetic_panel.yaml")
    split = raw["split"]
    assert isinstance(split, dict)
    raw["split"] = {**split, "min_assets_per_split": 1}
    config = RunConfig.from_mapping(raw)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        document = run_pipeline(config, output_directory=tmp_path).to_dict()
    assert document["min_assets_per_split"] == 1
    assert document["risks"] == []
    assert not any(issubclass(item.category, UserWarning) for item in caught)
    _assert_computed_model_metrics(document["metrics"])


def test_synthetic_metrics_repeat(load_example, tmp_path) -> None:
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        first = run_pipeline(config, output_directory=tmp_path / "first").to_dict()
        second = run_pipeline(config, output_directory=tmp_path / "second").to_dict()
    assert first["metrics"] == second["metrics"]
    assert (
        first["hist_gradient_boosting_iteration_count"]
        == second["hist_gradient_boosting_iteration_count"]
    )


def _assert_computed_model_metrics(metrics: object) -> None:
    assert isinstance(metrics, dict)
    for split_name in ("validation", "test"):
        block = metrics[split_name]
        assert isinstance(block, dict)
        for prefix in ("constant", "hist_gradient_boosting"):
            for suffix in ("root_mean_square_error", "mean_absolute_error", "nasa_score"):
                metric = block[f"{prefix}_{suffix}"]
                assert isinstance(metric, dict)
                assert metric["status"] == "COMPUTED"
                assert isinstance(metric["value"], float)


def _assert_headline_follows_validation_rmse(document: dict[str, object]) -> None:
    metrics = document["metrics"]
    assert isinstance(metrics, dict)
    validation = metrics["validation"]
    assert isinstance(validation, dict)
    constant_metric = validation["constant_root_mean_square_error"]
    tree_metric = validation["hist_gradient_boosting_root_mean_square_error"]
    assert isinstance(constant_metric, dict)
    assert isinstance(tree_metric, dict)
    constant_value = constant_metric["value"]
    tree_value = tree_metric["value"]
    assert isinstance(constant_value, float)
    assert isinstance(tree_value, float)
    if tree_value < constant_value:
        assert document["headline_model"] == "hist_gradient_boosting"
    else:
        assert document["headline_model"] == "constant"


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
