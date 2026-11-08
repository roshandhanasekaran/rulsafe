"""JSON shape for disabled, uncomputed, and computed metrics."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rulsafe.report import render_terminal_summary, write_json_report
from rulsafe.report.json import MetricComputationStatus, MetricValue


def test_disabled_metric_serialises_with_null_value() -> None:
    encoded = MetricValue.disabled().to_json()
    assert encoded == '{"value": null, "status": "DISABLED"}'
    assert json.loads(encoded) == {"value": None, "status": "DISABLED"}


def test_uncomputed_metric_serialises_with_null_value() -> None:
    encoded = MetricValue.not_computed().to_json()
    assert encoded == '{"value": null, "status": "NOT_COMPUTED"}'
    assert MetricValue.not_computed().status is MetricComputationStatus.NOT_COMPUTED


def test_computed_metric_keeps_its_number() -> None:
    encoded = MetricValue.computed(12.5).to_json()
    assert json.loads(encoded) == {"value": 12.5, "status": "COMPUTED"}


def test_absent_metrics_cannot_carry_a_number() -> None:
    for status in (MetricComputationStatus.DISABLED, MetricComputationStatus.NOT_COMPUTED):
        with pytest.raises(ValidationError):
            MetricValue(value=1.0, status=status)


def test_computed_metric_cannot_be_null() -> None:
    with pytest.raises(ValidationError):
        MetricValue(value=None, status=MetricComputationStatus.COMPUTED)


def test_computed_metric_must_be_finite() -> None:
    with pytest.raises(ValidationError):
        MetricValue.computed(float("nan"))


def test_boolean_is_not_a_metric_value() -> None:
    with pytest.raises(ValidationError):
        MetricValue(value=True, status=MetricComputationStatus.COMPUTED)


def test_json_report_writer_creates_a_strict_machine_readable_file(tmp_path: Path) -> None:
    document = {
        "title": "Equipment check",
        "metric": MetricValue.computed(12.5).to_dict(),
    }
    path = tmp_path / "nested" / "report.json"
    assert write_json_report(document, path) == path
    assert json.loads(path.read_text(encoding="utf-8")) == document
    assert path.read_bytes().endswith(b"\n")

    invalid_path = tmp_path / "invalid.json"
    with pytest.raises(ValueError, match="Out of range float"):
        write_json_report({"value": float("nan")}, invalid_path)
    assert not invalid_path.exists()


def test_terminal_summary_is_printable_and_includes_audit_context() -> None:
    summary = render_terminal_summary(
        {
            "title": "\x1b[31mPump\ncheck",
            "project": "pump-rul",
            "status": "COMPLETED",
            "asset_count": 12,
            "headline_model": "constant",
            "headline_split": "test",
            "headline_metrics": {"root_mean_square_error": {"value": 2.5, "status": "COMPUTED"}},
            "leakage": [
                {
                    "check_id": "future_in_features",
                    "status": "PASS",
                    "evidence": "Past rows only.",
                }
            ],
            "history_dispositions": [
                {
                    "asset_id": "pump-censored",
                    "support": "censored",
                    "disposition": "report",
                }
            ],
            "report_html": "reports/report.html",
        }
    )
    assert "\x1b" not in summary
    assert "Pump check" in summary
    assert "Status: COMPLETED" in summary
    assert "root_mean_square_error: 2.5 (COMPUTED)" in summary
    assert "[PASS] future_in_features: Past rows only." in summary
    assert "pump-censored: censored / report" in summary
    assert "HTML report: reports/report.html" in summary
    assert summary.endswith("\n")
