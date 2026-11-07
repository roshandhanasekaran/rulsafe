"""Command-line skeleton: help, version, schema validation, and explicit refusals."""

import warnings
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rulsafe._version import __version__
from rulsafe.cli import app

runner = CliRunner()


def test_help_lists_the_v01_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command_name in ("validate", "demo", "datasets", "train", "check"):
        assert command_name in result.stdout
    assert "safety-certified" in result.stdout


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_there_is_no_ui_command() -> None:
    result = runner.invoke(app, ["ui"])
    assert result.exit_code != 0


def test_validate_accepts_cmapss_and_rejects_scania(repository_root: Path) -> None:
    cmapss = repository_root / "examples" / "cmapss_fd001_completed_trajectory.yaml"
    accepted = runner.invoke(app, ["validate", "--config", str(cmapss)])
    assert accepted.exit_code == 0
    assert "cmapss-fd001-last-observation" in accepted.stdout

    scania = repository_root / "examples" / "scania_component_x.yaml"
    rejected = runner.invoke(app, ["validate", "--config", str(scania)])
    assert rejected.exit_code == 2
    assert "v0.2" in rejected.stdout


def test_demo_cmapss_is_not_implemented_and_scania_is_refused() -> None:
    cmapss = runner.invoke(app, ["demo", "cmapss"])
    assert cmapss.exit_code == 2
    assert "not downloaded" in cmapss.stdout.lower()
    assert "not computed" in cmapss.stdout.lower()

    scania = runner.invoke(app, ["demo", "scania"])
    assert scania.exit_code == 2
    assert "v0.2" in scania.stdout


def test_dataset_list_and_fetch_keep_licences_separate() -> None:
    listed = runner.invoke(app, ["datasets", "list"])
    assert listed.exit_code == 0
    assert "cmapss_fd001" in listed.stdout
    assert "not specified" in listed.stdout.lower()
    assert "CC BY 4.0" in listed.stdout
    assert "105" in listed.stdout

    fetched = runner.invoke(app, ["datasets", "fetch", "scania_component_x"])
    assert fetched.exit_code == 2
    assert "CC BY 4.0" in fetched.stdout
    assert "v0.2" in fetched.stdout

    cmapss_fetch = runner.invoke(app, ["datasets", "fetch", "cmapss_fd001"])
    assert cmapss_fetch.exit_code == 2
    assert "not specified" in cmapss_fetch.stdout.lower()
    assert "not implemented" in cmapss_fetch.stdout.lower()


def test_cached_cmapss_files_are_not_the_synthetic_slice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _self: True)
    result = runner.invoke(app, ["demo", "cmapss"])
    assert result.exit_code == 2
    assert "not implemented" in result.stdout.lower()


def test_demo_synthetic_writes_the_censored_asset(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        result = runner.invoke(app, ["demo", "synthetic", "--output", str(tmp_path)])
    assert result.exit_code == 0
    report = (tmp_path / "report.json").read_text(encoding="utf-8")
    assert "engine_e" in report
    assert "COMPUTED" in report
    assert "hist_gradient_boosting_root_mean_square_error" in report
    assert "below the minimum of 3" in report


def test_unknown_demo_and_dataset_are_usage_errors() -> None:
    unknown_demo = runner.invoke(app, ["demo", "bearings"])
    assert unknown_demo.exit_code == 2
    assert "Unknown demo" in unknown_demo.stdout

    unknown_dataset = runner.invoke(app, ["datasets", "fetch", "not-a-dataset"])
    assert unknown_dataset.exit_code == 2
    assert "Unknown dataset" in unknown_dataset.stdout


def test_missing_config_exits_with_usage_code(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    result = runner.invoke(app, ["validate", "--config", str(missing)])
    assert result.exit_code == 2


@pytest.mark.parametrize(
    "arguments",
    [
        ["init"],
        ["profile", "--config", "run.yaml"],
        ["check", "--config", "run.yaml"],
        ["train", "--config", "run.yaml"],
        ["report", "--run", "rulsafe-runs/demo"],
    ],
)
def test_unimplemented_commands_exit_with_usage_code(arguments: list[str]) -> None:
    result = runner.invoke(app, arguments)
    assert result.exit_code == 2
    assert "not implemented" in result.stdout.lower()
