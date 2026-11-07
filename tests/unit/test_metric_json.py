"""JSON shape for disabled, uncomputed, and computed metrics."""

import json

import pytest
from pydantic import ValidationError

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
