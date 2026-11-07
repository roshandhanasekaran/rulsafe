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
    assert result.report_paths.json_path is not None
    assert result.report_paths.json_path.is_file()
    copy_path = result.save_json(tmp_path / "copy.json")
    assert copy_path.read_text(encoding="utf-8") == result.report_paths.json_path.read_text(
        encoding="utf-8"
    )
