"""Release-facing input scenarios through the public API."""

import csv
import json
import warnings
from pathlib import Path

import pytest

from rulsafe import run_pipeline
from rulsafe.config import RunConfig
from rulsafe.exceptions import ConfigurationError, ContractError


def test_reordered_readings_produce_the_same_result(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    control = _copy_panel(repository_root, load_example, tmp_path / "control")
    reordered = _copy_panel(repository_root, load_example, tmp_path / "reordered")
    fields, rows = _read_csv(Path(reordered.connector.signals))
    _write_csv(Path(reordered.connector.signals), fields, list(reversed(rows)))

    first = _run(control, tmp_path / "control-run")
    second = _run(reordered, tmp_path / "reordered-run")
    assert first["metrics"] == second["metrics"]
    assert first["splits"] == second["splits"]
    assert first["preprocessing"] == second["preprocessing"]


def test_missing_cells_delays_constants_and_quoted_unicode_ids_complete(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    config = _copy_panel(repository_root, load_example, tmp_path / "stress")
    fields, rows = _read_csv(Path(config.connector.signals))
    for index, row in enumerate(rows):
        if row["asset_id"] == "engine_a":
            row["asset_id"] = "机组,01"
        row["pressure"] = "1"
        if index % 4 == 0:
            row["temperature"] = ""
        if index % 5 == 0:
            row["available_at"] = str(int(row["event_time"]) + 1)
    _write_csv(Path(config.connector.signals), fields, rows)
    for table_path in (Path(config.connector.assets), Path(config.connector.events)):
        table_fields, table_rows = _read_csv(table_path)
        for row in table_rows:
            if row["asset_id"] == "engine_a":
                row["asset_id"] = "机组,01"
        _write_csv(table_path, table_fields, table_rows)

    document = _run(config, tmp_path / "stress-run")
    assert document["status"] == "COMPLETED"
    split_ids = [asset_id for members in document["splits"].values() for asset_id in members]
    assert "机组,01" in split_ids


def test_missing_configured_sensor_column_stops_before_fit(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    config = _copy_panel(repository_root, load_example, tmp_path / "missing-column")
    fields, rows = _read_csv(Path(config.connector.signals))
    fields.remove("pressure")
    _write_csv(Path(config.connector.signals), fields, rows)
    with pytest.raises(ConfigurationError, match="missing configured columns: pressure"):
        run_pipeline(config, output_directory=tmp_path / "run")


@pytest.mark.parametrize(
    ("table_name", "column_name", "hidden_value"),
    [
        ("assets", "asset_id", "unknown-physical-machine"),
        ("signals", "temperature", "NOT_NUMERIC"),
    ],
)
def test_duplicate_csv_headers_cannot_hide_invalid_values(
    repository_root: Path,
    load_example,
    tmp_path: Path,
    table_name: str,
    column_name: str,
    hidden_value: str,
) -> None:
    config = _copy_panel(repository_root, load_example, tmp_path / "duplicate-header")
    path = Path(getattr(config.connector, table_name))
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    column_index = rows[0].index(column_name)
    rows[0].insert(column_index, column_name)
    for row in rows[1:]:
        row.insert(column_index, hidden_value)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)

    with pytest.raises(ConfigurationError, match=rf"duplicate column names: {column_name}"):
        run_pipeline(config, output_directory=tmp_path / "run")


def test_blank_csv_header_is_rejected(repository_root: Path, load_example, tmp_path: Path) -> None:
    config = _copy_panel(repository_root, load_example, tmp_path / "blank-header")
    path = Path(config.connector.signals)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    rows[0][rows[0].index("temperature")] = " "
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)

    with pytest.raises(ConfigurationError, match="blank column name"):
        run_pipeline(config, output_directory=tmp_path / "run")


@pytest.mark.parametrize("malformation", ["extra", "missing"])
def test_csv_row_width_must_match_its_header(
    repository_root: Path, load_example, tmp_path: Path, malformation: str
) -> None:
    config = _copy_panel(repository_root, load_example, tmp_path / f"row-{malformation}")
    path = Path(config.connector.signals)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if malformation == "extra":
        rows[1].append("unheaded")
    else:
        rows[1].pop()
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)

    with pytest.raises(ConfigurationError, match=r"row 2 has \d+ cells; the header has \d+"):
        run_pipeline(config, output_directory=tmp_path / "run")


def test_invalid_utf8_has_a_table_specific_error(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    config = _copy_panel(repository_root, load_example, tmp_path / "invalid-utf8")
    Path(config.connector.signals).write_bytes(b"\xff\xfe")
    with pytest.raises(ConfigurationError, match=r"signals\.csv is not valid UTF-8"):
        run_pipeline(config, output_directory=tmp_path / "run")


def test_terminal_asset_without_pre_event_readings_is_reported_and_excluded(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    config = _copy_panel(repository_root, load_example, tmp_path / "no-readings")
    fields, rows = _read_csv(Path(config.connector.signals))
    _write_csv(
        Path(config.connector.signals),
        fields,
        [row for row in rows if row["asset_id"] != "engine_a"],
    )

    document = _run(config, tmp_path / "run")
    assert "engine_a" in document["censored_or_unsupported_asset_ids"]
    assert all("engine_a" not in members for members in document["splits"].values())
    history = next(row for row in document["history_dispositions"] if row["asset_id"] == "engine_a")
    assert history["support"] == "unsupported"
    assert history["disposition"] == "report"


def test_event_for_unregistered_asset_fails_the_audit(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    config = _copy_panel(repository_root, load_example, tmp_path / "unknown-event")
    fields, rows = _read_csv(Path(config.connector.events))
    rows.append(
        {
            "asset_id": "ghost",
            "event_time": "2",
            "available_at": "2",
            "event_type": "failure",
            "failure_notes": "unregistered",
        }
    )
    _write_csv(Path(config.connector.events), fields, rows)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with pytest.raises(ContractError, match="unsupported_history"):
            run_pipeline(config, output_directory=tmp_path / "run")
    document = json.loads((tmp_path / "run" / "report.json").read_text(encoding="utf-8"))
    assert document["status"] == "FAILED"
    finding = next(row for row in document["leakage"] if row["check_id"] == "unsupported_history")
    assert finding["status"] == "CONFIRMED"
    assert "ghost" in finding["evidence"]


def _copy_panel(repository_root: Path, load_example, destination: Path) -> RunConfig:
    destination.mkdir()
    source = repository_root / "tests" / "fixtures" / "synthetic_panel"
    for name in ("assets.csv", "signals.csv", "events.csv"):
        text = (source / name).read_text(encoding="utf-8")
        (destination / name).write_text(text, encoding="utf-8")
    raw = load_example("synthetic_panel.yaml")
    connector = raw["connector"]
    assert isinstance(connector, dict)
    raw["connector"] = {
        **connector,
        "assets": str(destination / "assets.csv"),
        "signals": str(destination / "signals.csv"),
        "events": str(destination / "events.csv"),
    }
    return RunConfig.from_mapping(raw)


def _run(config: RunConfig, output: Path) -> dict[str, object]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return run_pipeline(config, output_directory=output).to_dict()


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
