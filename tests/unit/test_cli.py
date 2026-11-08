"""Command-line skeleton: help, version, schema validation, and explicit refusals."""

import json
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
    assert "cmapss-fd001-completed-trajectory" in accepted.stdout

    scania = repository_root / "examples" / "scania_component_x.yaml"
    rejected = runner.invoke(app, ["validate", "--config", str(scania)])
    assert rejected.exit_code == 2
    assert "v0.2" in rejected.stdout


def test_demo_cmapss_without_tables_tells_you_to_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    real_is_file = Path.is_file

    def hide_cmapss_tables(self: Path) -> bool:
        if "cmapss" in self.parts and self.suffix in {".parquet", ".txt"}:
            return False
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", hide_cmapss_tables)
    cmapss = runner.invoke(app, ["demo", "cmapss"])
    assert cmapss.exit_code == 2
    assert "data fetch cmapss" in cmapss.stdout
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

    refused = runner.invoke(app, ["data", "fetch", "cmapss", "--from-file", "missing-cmapss.zip"])
    assert refused.exit_code == 2
    assert "could not read archive" in refused.stdout.lower()
    unknown = runner.invoke(app, ["data", "fetch", "scania"])
    assert unknown.exit_code == 2
    assert "unknown dataset" in unknown.stdout.lower()


def test_data_fetch_from_file_uses_the_local_archive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Path | None] = {}

    def fake_fetch(destination: Path, *, archive: Path | None = None) -> Path:
        seen["destination"] = destination
        seen["archive"] = archive
        return destination

    monkeypatch.setattr("rulsafe.datasets.cmapss_convert.fetch_cmapss_fd001", fake_fetch)
    archive = tmp_path / "CMAPSSData.zip"
    archive.write_bytes(b"local")
    result = runner.invoke(
        app,
        ["data", "fetch", "cmapss", "--from-file", str(archive), "--output", str(tmp_path / "out")],
    )
    assert result.exit_code == 0
    assert seen["archive"] == archive
    assert seen["destination"] == tmp_path / "out"
    assert "not specified" in result.stdout.lower()


def test_demo_synthetic_writes_the_censored_asset(tmp_path: Path) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        result = runner.invoke(app, ["demo", "synthetic", "--output", str(tmp_path)])
    assert result.exit_code == 0
    report = (tmp_path / "report.json").read_text(encoding="utf-8")
    assert "unit-censored" in report
    assert "COMPUTED" in report
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "Research software" in html
    assert "report.html" in result.stdout
    assert "headline evaluation" in report
    assert "used for early stopping/selection" in report
    assert "hist_gradient_boosting_root_mean_square_error" in report
    assert "below the minimum of 3" not in report
    assert not any(issubclass(item.category, UserWarning) for item in caught)


def test_demos_work_without_a_checkout_in_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Installed demos use trusted configs, not a relative examples directory."""
    monkeypatch.chdir(tmp_path)
    examples = tmp_path / "examples"
    examples.mkdir()
    (examples / "synthetic_fleet.yaml").write_text("invalid: true\n", encoding="utf-8")
    result = runner.invoke(app, ["demo", "synthetic"])
    assert result.exit_code == 0, result.stdout
    document = json.loads((tmp_path / "rulsafe-runs/synthetic/report.json").read_text())
    assert document["project"] == "synthetic-fleet"
    assert document["censored_or_unsupported_asset_ids"] == ["unit-censored"]
    cmapss = runner.invoke(app, ["demo", "cmapss"])
    assert cmapss.exit_code == 2
    assert "data fetch cmapss" in cmapss.stdout
    assert "Could not read configuration" not in cmapss.stdout


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
