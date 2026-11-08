"""JSON report.

The JSON artefact mirrors the HTML sections so a caller can read leakage
status, history dispositions, and which sections are not covered without
parsing HTML.

A metric is always an object. A disabled or uncomputed metric serialises as
``{"value": null, "status": "DISABLED"}`` or
``{"value": null, "status": "NOT_COMPUTED"}``. A computed metric uses the
same keys with a finite number and ``"status": "COMPUTED"``.
"""

import json
import math
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, model_validator


class MetricComputationStatus(StrEnum):
    """Whether a report metric has a number.

    ``DISABLED`` means the run was not asked to compute it.
    ``NOT_COMPUTED`` means it was in scope but this run has no number yet.
    Neither status is a zero and neither is a pass.
    """

    COMPUTED = "COMPUTED"
    DISABLED = "DISABLED"
    NOT_COMPUTED = "NOT_COMPUTED"


def _reject_boolean_metric(value: object) -> object:
    """Reject a boolean passed where a metric number or null is required.

    Args:
        value: Raw metric value.

    Returns:
        The same value when it is not a boolean.

    Raises:
        ValueError: ``True`` or ``False`` was supplied.
    """
    if isinstance(value, bool):
        raise ValueError("A metric value must be a number or null, not a boolean.")
    return value


class MetricValue(BaseModel):
    """One numeric report field, or an explicit reason it has no number.

    Attributes:
        value: The number, or null when the metric is disabled or uncomputed.
        status: ``COMPUTED``, ``DISABLED``, or ``NOT_COMPUTED``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: Annotated[float | None, BeforeValidator(_reject_boolean_metric)] = None
    status: MetricComputationStatus

    @model_validator(mode="after")
    def value_matches_status(self) -> "MetricValue":
        """Keep null values and numeric values on the right statuses.

        Returns:
            This metric when the value and status agree.

        Raises:
            ValueError: A disabled or uncomputed metric has a number, or a
                computed metric is null or not finite.
        """
        absent = self.status in {
            MetricComputationStatus.DISABLED,
            MetricComputationStatus.NOT_COMPUTED,
        }
        if absent and self.value is not None:
            raise ValueError("A disabled or uncomputed metric must serialise value as null.")
        computed_without_number = self.status is MetricComputationStatus.COMPUTED and (
            self.value is None or not math.isfinite(self.value)
        )
        if computed_without_number:
            raise ValueError("A computed metric must have a finite numeric value.")
        return self

    @classmethod
    def computed(cls, value: float) -> "MetricValue":
        """Build a metric that has a finite number.

        Args:
            value: Computed score.

        Returns:
            A metric with status ``COMPUTED``.
        """
        return cls(value=value, status=MetricComputationStatus.COMPUTED)

    @classmethod
    def disabled(cls) -> "MetricValue":
        """Build a metric the run was not asked to compute.

        Returns:
            ``{"value": null, "status": "DISABLED"}`` once serialised.
        """
        return cls(value=None, status=MetricComputationStatus.DISABLED)

    @classmethod
    def not_computed(cls) -> "MetricValue":
        """Build a metric that is in scope but has no number yet.

        Returns:
            ``{"value": null, "status": "NOT_COMPUTED"}`` once serialised.
        """
        return cls(value=None, status=MetricComputationStatus.NOT_COMPUTED)

    def to_dict(self) -> dict[str, float | str | None]:
        """Return the JSON object for this metric.

        Returns:
            ``value`` then ``status``. ``value`` is None when there is no number,
            which :func:`json.dumps` writes as null.
        """
        return {"value": self.value, "status": self.status.value}

    def to_json(self) -> str:
        """Serialise this metric as one JSON object.

        Returns:
            A JSON object with ``value`` and ``status``.
        """
        return json.dumps(self.to_dict())


def write_json_report(report_document: Mapping[str, object], path: Path) -> Path:
    """Write the machine-readable report.

    Args:
        report_document: Report fields, including leakage coverage.
        path: Destination path.

    Returns:
        The path that was written.

    Raises:
        TypeError: A report value is not JSON serialisable.
        ValueError: A report value is a non-finite number.
    """
    encoded = json.dumps(dict(report_document), indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")
    return path
