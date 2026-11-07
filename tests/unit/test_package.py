"""Package metadata and import boundaries."""

import sys
from importlib.metadata import version

from rulsafe import __version__, run_pipeline
from rulsafe.config import RunConfig


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
    assert "excluded from training" in entry["detail"]
    assert result.report_paths.json_path is not None
    assert result.report_paths.json_path.is_file()
    copy_path = result.save_json(tmp_path / "copy.json")
    assert copy_path.read_text(encoding="utf-8") == result.report_paths.json_path.read_text(
        encoding="utf-8"
    )


def test_reject_policy_excludes_the_censored_engine(load_example, tmp_path) -> None:
    raw = load_example("synthetic_panel.yaml")
    labeling = raw["labeling"]
    assert isinstance(labeling, dict)
    raw["labeling"] = {**labeling, "censored_policy": "reject"}
    config = RunConfig.from_mapping(raw)
    document = run_pipeline(config, output_directory=tmp_path).to_dict()
    assert document["dropped_asset_ids"] == []
    for split_name in ("train", "validation", "test"):
        assert "engine_e" not in document["splits"][split_name]
    entry = _disposition(document, "engine_e")
    assert entry["support"] == "censored"
    assert entry["disposition"] == "reject"
    assert entry["used_for_training"] is False
    assert entry["detail"] == (
        "Rejected and excluded from training. "
        "A censored or unsupported history is not a training row."
    )


def _disposition(document: dict[str, object], asset_id: str) -> dict[str, object]:
    rows = document["history_dispositions"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        if row.get("asset_id") == asset_id:
            return row
    raise AssertionError(f"{asset_id} has no history disposition")
