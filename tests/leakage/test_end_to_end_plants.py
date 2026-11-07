"""Planted leaks that travel through ``run_pipeline`` and write a FAILED report.

Window-level checks stay at the function fixtures. A correct causal builder
never emits a future row, a delayed row, a post-event row, or a mixed-asset
window, so those checks cannot be confirmed by feeding the builder bad CSV.
The plants here are rows, event tables, an official RUL file, or a protocol
string stored after schema validation. YAML still rejects ``random`` and
``linear``.
"""

import csv
import json
import warnings
from pathlib import Path

from rulsafe import run_pipeline
from rulsafe.config import LeakageStatus, OfficialBenchmarkConfig, RunConfig, ScalerName
from rulsafe.contract import LogicalTableRole
from rulsafe.exceptions import ContractError
from rulsafe.io.files import LoadedTable
from rulsafe.leakage.fail_on import future_labels_finding, scaler_leakage_finding
from rulsafe.mapping import LogicalTables
from rulsafe.pipeline.execute import (
    _observed_label_triples,
    _training_targets_match_official_file,
)
from rulsafe.pipeline.prepare import ScoredRow
from rulsafe.pipeline.preprocess import fit_preprocessors

_TABLE_NAMES = ("assets.csv", "signals.csv", "events.csv")


def test_clean_panel_passes_fail_on_and_warns_on_association(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    """The untouched panel completes, and every fail_on check passes."""
    config = _panel_config(repository_root, load_example, tmp_path)
    document, error = _run(config, tmp_path / "run")
    assert error is None
    assert document["status"] == "COMPLETED"
    findings = _findings(document)
    for check_id, finding in findings.items():
        if check_id == "high_association_with_label":
            continue
        if check_id == "backend_internal_split":
            continue
        assert finding["status"] == "PASS"
    association = findings["high_association_with_label"]
    assert association["status"] == "WARNING"
    assert "pressure" in association["evidence"]
    assert "engine_e" in findings["unsupported_history"]["evidence"]
    assert "training assets only" in findings["scaler_leakage"]["evidence"]
    assert "None of them are in the test split" in findings["test_used_for_choices"]["evidence"]
    assert "Early stopping used" in findings["test_used_for_choices"]["evidence"]
    assert (
        "no official hidden-label file"
        in findings["official_hidden_label_reconstruction"]["evidence"]
    )


def test_replacement_inside_the_span_confirms_and_fails_the_report(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    """A replacement strictly inside the signal span is a real CONFIRMED run."""
    config = _panel_config(repository_root, load_example, tmp_path)
    _append_event(config, "engine_a", "1", "replacement")
    _assert_failed(config, tmp_path / "run", "replacement_episode_mix")


def test_pressure_copied_from_the_target_confirms(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    """An allowed column that equals remaining life is CONFIRMED."""
    config = _panel_config(repository_root, load_example, tmp_path)
    fields, rows = _read_csv(Path(config.connector.signals))
    for row in rows:
        if row["asset_id"] == "engine_e":
            continue
        row["pressure"] = str(2 - int(row["event_time"]))
    _write_csv(Path(config.connector.signals), fields, rows)
    document = _assert_failed(config, tmp_path / "run", "target_in_features")
    evidence = _findings(document)["target_in_features"]["evidence"]
    assert "pressure" in evidence


def test_auto_features_pick_up_failure_notes(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    """``feature_columns: auto`` keeps a forbidden column that an allowlist would reject."""
    config = _panel_config(repository_root, load_example, tmp_path)
    fields, rows = _read_csv(Path(config.connector.signals))
    fields.append("failure_notes")
    for row in rows:
        row["failure_notes"] = "1"
    _write_csv(Path(config.connector.signals), fields, rows)
    config = config.model_copy(
        update={"signals": config.signals.model_copy(update={"feature_columns": "auto"})}
    )
    _assert_failed(config, tmp_path / "run", "event_metadata_in_features")


def test_failure_and_censor_on_one_engine_is_a_silent_negative(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    """A competing close on a failed engine is still a censored id, and it is labeled."""
    config = _panel_config(repository_root, load_example, tmp_path)
    _append_event(config, "engine_e", "2", "failure")
    document = _assert_failed(config, tmp_path / "run", "silent_negative_censoring")
    assert "unsupported_history" in document["confirmed_fail_on"]


def test_signal_asset_missing_from_the_asset_table_is_unsupported(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    """A signal id with no failure and no asset row must be named, and is not."""
    config = _panel_config(repository_root, load_example, tmp_path)
    fields, rows = _read_csv(Path(config.connector.signals))
    rows.append(
        {
            "asset_id": "engine_h",
            "event_time": "0",
            "available_at": "0",
            "temperature": "1",
            "pressure": "1",
        }
    )
    _write_csv(Path(config.connector.signals), fields, rows)
    document = _assert_failed(config, tmp_path / "run", "unsupported_history")
    assert "engine_h" in _findings(document)["unsupported_history"]["evidence"]
    assert _findings(document)["silent_negative_censoring"]["status"] == "PASS"


def test_official_file_that_names_training_engines_confirms(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    """Overlap with the RUL file confirms even when the file value is not the label."""
    config = _panel_config(repository_root, load_example, tmp_path)
    rul_path = tmp_path / "rul.txt"
    lines = [f"engine_{suffix} 999" for suffix in ("a", "b", "c", "d", "e", "f", "g")]
    rul_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    benchmark = OfficialBenchmarkConfig(protocol="fd001_last_observation", rul_path=rul_path)
    config = config.model_copy(
        update={
            "evaluation": config.evaluation.model_copy(update={"official_benchmark": benchmark})
        }
    )
    document = _assert_failed(config, tmp_path / "run", "official_hidden_label_reconstruction")
    assert "overlap" in _findings(document)["official_hidden_label_reconstruction"]["evidence"]


def test_stored_random_protocol_confirms_after_validation(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    """A protocol string stored past the schema still reaches the real checker."""
    config = _panel_config(repository_root, load_example, tmp_path)
    config = config.model_copy(
        update={"split": config.split.model_copy(update={"protocol": "random"})}
    )
    _assert_failed(config, tmp_path / "run", "random_split")


def test_stored_linear_gap_confirms_after_validation(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    """A gap name stored past the schema still reaches the real checker."""
    config = _panel_config(repository_root, load_example, tmp_path)
    config = config.model_copy(
        update={"signals": config.signals.model_copy(update={"gap_policy": "linear"})}
    )
    _assert_failed(config, tmp_path / "run", "interpolation_leak")


def test_tracked_sensor_warns_and_the_run_completes(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    """A feature that tracks the target warns and does not abort the run."""
    config = _panel_config(repository_root, load_example, tmp_path)
    fields, rows = _read_csv(Path(config.connector.signals))
    for row in rows:
        if row["asset_id"] == "engine_e":
            continue
        row["temperature"] = str(3 * (2 - int(row["event_time"])))
    _write_csv(Path(config.connector.signals), fields, rows)
    document, error = _run(config, tmp_path / "run")
    assert error is None
    assert document["status"] == "COMPLETED"
    association = _findings(document)["high_association_with_label"]
    assert association["status"] == "WARNING"
    assert "temperature" in association["evidence"]
    assert _findings(document)["target_in_features"]["status"] == "PASS"


def test_label_triples_come_from_the_event_table(load_example) -> None:
    """A label that disagrees with the event time is CONFIRMED even when it was stored as-is."""
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    events = LoadedTable(
        role=LogicalTableRole.EVENTS,
        path=Path("events.csv"),
        row_count=1,
        rows=(
            {
                "asset_id": "engine_a",
                "event_time": "2",
                "available_at": "2",
                "event_type": "failure",
                "failure_notes": "bearing",
            },
        ),
    )
    empty = LoadedTable(role=LogicalTableRole.ASSETS, path=Path("assets.csv"), row_count=0, rows=())
    tables = LogicalTables(assets=empty, signals=empty, events=events)
    row = ScoredRow(
        asset_id="engine_a",
        prediction_time=0.0,
        features={},
        remaining_life=9.0,
    )
    finding = future_labels_finding(_observed_label_triples((row,), tables, config), None)
    assert finding.status is LeakageStatus.CONFIRMED
    assert "9.0" in finding.evidence


def test_preprocessor_records_the_assets_it_was_fit_on() -> None:
    """Scaler leakage compares the recorded fit ids with the training split."""
    fitted = fit_preprocessors(
        ({"temperature": 1.0}, {"temperature": 2.0}),
        asset_ids=("train-a", "held-out"),
        feature_names=("temperature",),
        clip_percentiles=(1.0, 99.0),
        scaler=ScalerName.STANDARD,
    )
    assert fitted.fitted_asset_ids == ("train-a", "held-out")
    finding = scaler_leakage_finding(fitted.fitted_asset_ids, ("train-a",))
    assert finding.status is LeakageStatus.CONFIRMED
    assert "held-out" in finding.evidence


def test_training_label_match_reads_the_official_file() -> None:
    """The official-file flag is true only when a training target equals that asset's file value."""
    matched = ScoredRow("train-a", 0.0, {}, 10.0)
    other = ScoredRow("train-b", 0.0, {}, 4.0)
    assert _training_targets_match_official_file((matched,), {"train-a": 10.0}, None) is True
    assert _training_targets_match_official_file((other,), {"train-a": 10.0}, None) is False
    assert _training_targets_match_official_file((matched,), {"train-a": 999.0}, None) is False


def _panel_config(repository_root: Path, load_example, tmp_path: Path) -> RunConfig:
    """Copy the panel into ``tmp_path`` and point a validated config at the copy."""
    source = repository_root / "tests" / "fixtures" / "synthetic_panel"
    destination = tmp_path / "tables"
    destination.mkdir()
    for name in _TABLE_NAMES:
        text = (source / name).read_text(encoding="utf-8")
        (destination / name).write_text(text, encoding="utf-8")
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    connector = config.connector.model_copy(
        update={
            "assets": destination / "assets.csv",
            "signals": destination / "signals.csv",
            "events": destination / "events.csv",
        }
    )
    return config.model_copy(update={"connector": connector})


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Return the header and the rows of a CSV file."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    """Rewrite a CSV file."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _append_event(config: RunConfig, asset_id: str, event_time: str, event_type: str) -> None:
    """Add one event row to the config's event file."""
    path = Path(config.connector.events)
    fields, rows = _read_csv(path)
    rows.append(
        {
            "asset_id": asset_id,
            "event_time": event_time,
            "available_at": event_time,
            "event_type": event_type,
            "failure_notes": "planted",
        }
    )
    _write_csv(path, fields, rows)


def _run(config: RunConfig, output: Path) -> tuple[dict[str, object], ContractError | None]:
    """Run the pipeline and return the written report."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        try:
            result = run_pipeline(config, output_directory=output)
        except ContractError as error:
            document = json.loads((output / "report.json").read_text(encoding="utf-8"))
            return document, error
    return result.to_dict(), None


def _assert_failed(config: RunConfig, output: Path, check_id: str) -> dict[str, object]:
    """Require a CONFIRMED check, a FAILED report, and the HTML copy."""
    document, error = _run(config, output)
    assert error is not None
    assert check_id in str(error)
    assert document["status"] == "FAILED"
    confirmed = document["confirmed_fail_on"]
    assert isinstance(confirmed, list)
    assert check_id in confirmed
    html = (output / "report.html").read_text(encoding="utf-8")
    assert "FAILED" in html
    return document


def _findings(document: dict[str, object]) -> dict[str, dict[str, str]]:
    """Index leakage findings by check id."""
    raw = document["leakage"]
    assert isinstance(raw, list)
    found: dict[str, dict[str, str]] = {}
    for item in raw:
        assert isinstance(item, dict)
        found[str(item["check_id"])] = {
            "status": str(item["status"]),
            "evidence": str(item["evidence"]),
        }
    return found
