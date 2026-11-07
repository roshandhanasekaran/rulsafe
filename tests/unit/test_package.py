"""Package metadata and import boundaries."""

import sys
from importlib.metadata import version

import pytest

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


def test_run_pipeline_is_not_implemented(load_example) -> None:
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    with pytest.raises(NotImplementedError):
        run_pipeline(config)
