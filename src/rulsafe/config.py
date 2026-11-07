"""Run configuration schema.

v0.1 checks a completed-trajectory remaining-useful-life run. The YAML file
is the contract. This module does not read telemetry, fit a model, or write
a report. Censored fleet tasks are rejected instead of being silently ignored.
"""

import math
from collections.abc import Mapping, Sequence
from enum import Enum, StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from rulsafe.contract import (
    GapPolicy,
    TimestampType,
    column_is_identifier,
    column_is_target_name,
    parse_gap_policy,
    reject_random_split,
    table_suffix_is_supported,
)
from rulsafe.exceptions import ConfigurationError
from rulsafe.models.forbid_persistence import reject_persistence_baseline


class SplitProtocol(StrEnum):
    """Named way to build train, validation, and final test.

    ``global_time`` is deferred to v0.2 and is rejected rather than ignored.
    """

    OFFICIAL_PARTITIONS = "official_partitions"
    GROUP_HOLDOUT = "group_holdout"


class LabelTask(StrEnum):
    """v0.1 prediction question.

    ``completed_trajectory_rul`` is remaining useful life on a trajectory that
    runs to a known end. ``cmapss_last_observation`` scores only the last cycle
    of each C-MAPSS test engine. Censored fleet tasks, including SCANIA, are
    rejected here and belong to v0.2.
    """

    COMPLETED_TRAJECTORY_RUL = "completed_trajectory_rul"
    CMAPSS_LAST_OBSERVATION = "cmapss_last_observation"


class TimeUnit(StrEnum):
    """Unit of ``labeling.horizon`` and alert lead time."""

    HOURS = "hours"
    DAYS = "days"
    CYCLES = "cycles"
    STEPS = "steps"


class CensoredHistoryPolicy(StrEnum):
    """What v0.1 does with a censored or unsupported history.

    Histories are never removed without a finding. ``reject`` stops the run.
    ``report`` keeps an explicit audit row and leaves the history out of the loss.
    """

    REJECT = "reject"
    REPORT = "report"


class ScalerName(StrEnum):
    """Train-only scaler. Fitting it on another split is leakage."""

    NONE = "none"
    STANDARD = "standard"
    MINMAX = "minmax"


class BaselineName(StrEnum):
    """v0.1 baselines. Persistence, age, and logistic regression are not members."""

    CONSTANT = "constant"
    HIST_GRADIENT_BOOSTING = "hist_gradient_boosting"


class LeakageStatus(StrEnum):
    """Outcome of one leakage check.

    A report must not collapse these into a global "no leakage" claim.
    """

    CONFIRMED = "CONFIRMED"
    WARNING = "WARNING"
    NOT_CHECKED = "NOT_CHECKED"
    # "PASS" is a leakage-audit status, not a password. Bandit B105 matches the name.
    PASS = "PASS"  # noqa: S105  # nosec B105


class LeakageCheckId(StrEnum):
    """Identifier of a leakage check.

    ``scaler_leakage`` also covers the transformer membership manifest.
    ``unsupported_history`` is the v0.1 check that a censored or unsupported
    trajectory was dropped or relabeled without a finding.
    """

    RANDOM_SPLIT = "random_split"
    FUTURE_LABELS = "future_labels"
    FUTURE_IN_FEATURES = "future_in_features"
    POST_EVENT_FEATURES = "post_event_features"
    DELAYED_RECORD_LEAK = "delayed_record_leak"
    INTERPOLATION_LEAK = "interpolation_leak"
    ENTITY_LEAKAGE = "entity_leakage"
    SCALER_LEAKAGE = "scaler_leakage"
    TARGET_IN_FEATURES = "target_in_features"
    EVENT_METADATA_IN_FEATURES = "event_metadata_in_features"
    SILENT_NEGATIVE_CENSORING = "silent_negative_censoring"
    UNSUPPORTED_HISTORY = "unsupported_history"
    REPLACEMENT_EPISODE_MIX = "replacement_episode_mix"
    TEST_USED_FOR_CHOICES = "test_used_for_choices"
    OFFICIAL_HIDDEN_LABEL_RECONSTRUCTION = "official_hidden_label_reconstruction"
    HIGH_ASSOCIATION_WITH_LABEL = "high_association_with_label"
    BACKEND_INTERNAL_SPLIT = "backend_internal_split"


class SplitReportName(StrEnum):
    """A split that can appear in the report."""

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class PlotName(StrEnum):
    """A plot the report will include once plotting exists.

    The first three are the v0.1 completed-trajectory plots. Alert plots are
    rejected: alerts are deferred to v0.2.
    """

    PREDICTION_ERROR = "prediction_error"
    ERROR_BY_UNIT = "error_by_unit"
    HISTORY_DISPOSITIONS = "history_dispositions"
    PRECISION_RECALL = "pr_curve"
    CALIBRATION = "calibration"
    LABEL_COUNTS = "label_counts"


class ReportFormat(StrEnum):
    """An output file format. HTML and JSON are required together."""

    HTML = "html"
    JSON = "json"
    MARKDOWN = "markdown"


DEFAULT_FAIL_ON_CHECKS: tuple[LeakageCheckId, ...] = (
    LeakageCheckId.RANDOM_SPLIT,
    LeakageCheckId.FUTURE_LABELS,
    LeakageCheckId.FUTURE_IN_FEATURES,
    LeakageCheckId.POST_EVENT_FEATURES,
    LeakageCheckId.DELAYED_RECORD_LEAK,
    LeakageCheckId.INTERPOLATION_LEAK,
    LeakageCheckId.ENTITY_LEAKAGE,
    LeakageCheckId.SCALER_LEAKAGE,
    LeakageCheckId.TARGET_IN_FEATURES,
    LeakageCheckId.EVENT_METADATA_IN_FEATURES,
    LeakageCheckId.SILENT_NEGATIVE_CENSORING,
    LeakageCheckId.UNSUPPORTED_HISTORY,
    LeakageCheckId.REPLACEMENT_EPISODE_MIX,
    LeakageCheckId.TEST_USED_FOR_CHOICES,
    LeakageCheckId.OFFICIAL_HIDDEN_LABEL_RECONSTRUCTION,
)

DEFAULT_WARN_ON_CHECKS: tuple[LeakageCheckId, ...] = (
    LeakageCheckId.HIGH_ASSOCIATION_WITH_LABEL,
    LeakageCheckId.BACKEND_INTERNAL_SPLIT,
)

_REQUIRED_REPORT_FORMATS = frozenset({ReportFormat.HTML, ReportFormat.JSON})
_REPORT_SPLITS = frozenset(
    {SplitReportName.TRAIN, SplitReportName.VALIDATION, SplitReportName.TEST}
)


class StrictConfigModel(BaseModel):
    """Configuration object that rejects unknown keys and frozen after validation."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def _string_key_mapping(value: object) -> dict[str, object] | None:
    """Return a string-keyed copy of a mapping, or None when value is not a mapping.

    Args:
        value: Raw input passed to a before-validator.

    Returns:
        A copy with string keys, or None when ``value`` is not a dictionary.

    Raises:
        ValueError: A dictionary key is not a string.
    """
    if not isinstance(value, dict):
        return None
    mapping: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("Configuration keys must be strings.")
        mapping[key] = item
    return mapping


def _require_unique(values: Sequence[Enum], label: str) -> None:
    """Reject a repeated entry in a configuration list.

    Args:
        values: Parsed enum values.
        label: Human name of the list, used in the error.

    Raises:
        ValueError: The same value appears more than once.
    """
    seen: set[Enum] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Duplicate {label}: {value.value}.")
        seen.add(value)


def _folded(names: Sequence[str]) -> set[str]:
    """Return case-folded names.

    Args:
        names: Configured names.

    Returns:
        The names compared without regard to case.
    """
    return {name.casefold() for name in names}


def _overlap_message(left: Sequence[str], right: Sequence[str], message: str) -> None:
    """Raise when two name lists share a case-folded entry.

    Args:
        left: First name list.
        right: Second name list.
        message: Sentence prefix for the error.

    Raises:
        ValueError: The lists overlap.
    """
    shared = _folded(left) & _folded(right)
    if shared:
        rendered = ", ".join(sorted(shared))
        raise ValueError(f"{message}: {rendered}.")


def _parse_gap_policy_value(value: object) -> object:
    """Parse a gap policy and reject linear interpolation.

    Args:
        value: Raw ``gap_policy`` value.

    Returns:
        A :class:`GapPolicy` when ``value`` is a string, otherwise ``value``.

    Raises:
        ValueError: The policy is interpolation or is unknown.
    """
    if not isinstance(value, str):
        return value
    try:
        return parse_gap_policy(value)
    except ConfigurationError as error:
        raise ValueError(str(error)) from error


_GLOBAL_TIME_DEFERRED = (
    "global_time is deferred to v0.2. v0.1 accepts official_partitions and group_holdout."
)
_ALERTS_DEFERRED = (
    "alerts are deferred to v0.2. "
    "v0.1 does not accept an alert block, an alerts block, or alert plots."
)
_ALERT_PLOT_NAMES = frozenset({"alert_lead_times", "alerts"})


def _parse_protocol_value(value: object) -> object:
    """Parse a split protocol and reject ``random`` and ``global_time``.

    Args:
        value: Raw protocol value.

    Returns:
        The normalized protocol string, or ``value`` when it is not a string.

    Raises:
        ValueError: The protocol is ``random`` or the deferred ``global_time`` protocol.
    """
    if not isinstance(value, str):
        return value
    if value.strip().casefold() == "global_time":
        raise ValueError(_GLOBAL_TIME_DEFERRED)
    try:
        return reject_random_split(value)
    except ConfigurationError as error:
        raise ValueError(str(error)) from error


def _parse_baseline_value(value: object) -> object:
    """Parse a baseline name and reject persistence.

    Args:
        value: Raw model name.

    Returns:
        The normalized baseline name, or ``value`` when it is not a string.

    Raises:
        ValueError: The name is persistence, deferred past v0.1, or unknown.
    """
    if not isinstance(value, str):
        return value
    try:
        cleaned = reject_persistence_baseline(value)
    except ConfigurationError as error:
        raise ValueError(str(error)) from error
    normalized = cleaned.casefold()
    if normalized in {"age", "logistic", "logistic_regression"}:
        raise ValueError(
            f"Baseline {normalized!r} is not part of v0.1. "
            "v0.1 fits constant and hist_gradient_boosting."
        )
    allowed = {item.value for item in BaselineName}
    if normalized not in allowed:
        choices = ", ".join(item.value for item in BaselineName)
        raise ValueError(f"Unknown baseline {value!r}. Choose from: {choices}.")
    return normalized


_V02_LABEL_TASKS: dict[str, str] = {
    "failure_within_horizon": (
        "failure_within_horizon is a censored fleet task and is not part of v0.1. "
        "v0.1 scores completed trajectories. Use completed_trajectory_rul or "
        "cmapss_last_observation."
    ),
    "scania_five_class_last_readout": (
        "scania_five_class_last_readout is the SCANIA Component X adapter and is not "
        "part of v0.1. SCANIA moves to v0.2."
    ),
}

_SILENT_CENSOR_POLICIES: frozenset[str] = frozenset(
    {
        "exclude_from_loss",
        "drop",
        "drop_unlabelled",
        "drop_unlabeled",
        "ignore",
        "silent",
    }
)


def _parse_label_task(value: object) -> object:
    """Parse a v0.1 label task and reject censored fleet tasks.

    Args:
        value: Raw ``labeling.task`` value.

    Returns:
        The normalized task name, or ``value`` when it is not a string.

    Raises:
        ValueError: The task is a v0.2 fleet question.
    """
    if not isinstance(value, str):
        return value
    normalized = value.strip().casefold()
    deferred_message = _V02_LABEL_TASKS.get(normalized)
    if deferred_message is not None:
        raise ValueError(deferred_message)
    return normalized


def _parse_feature_columns(value: object) -> object:
    """Accept ``auto`` or leave a list for later validation.

    Args:
        value: Raw ``feature_columns`` value.

    Returns:
        ``auto`` or the original value.

    Raises:
        ValueError: A string other than ``auto`` was provided.
    """
    if isinstance(value, str) and value.strip().casefold() != "auto":
        raise ValueError("feature_columns must be 'auto' or a list of column names.")
    if isinstance(value, str):
        return "auto"
    return value


def _parse_threshold_split(value: object) -> object:
    """Accept only the validation split for threshold selection.

    Args:
        value: Raw ``threshold_split`` value.

    Returns:
        ``validation`` when the input is that word.

    Raises:
        ValueError: Any other split was requested.
    """
    if isinstance(value, str) and value.strip().casefold() != "validation":
        raise ValueError(
            "Thresholds are chosen on the validation split only. "
            "threshold_split must be validation."
        )
    if isinstance(value, str):
        return "validation"
    return value


def _require_consistent_gap(gap_policy: GapPolicy, maximum_gap: int | None) -> None:
    """Require ``max_gap`` if and only if the policy is forward fill.

    Args:
        gap_policy: Parsed gap policy.
        maximum_gap: Configured maximum gap, or None.

    Raises:
        ValueError: The gap settings contradict each other.
    """
    if gap_policy is GapPolicy.FORWARD_FILL and maximum_gap is None:
        raise ValueError("max_gap is required when gap_policy is ffill.")
    if gap_policy is GapPolicy.NONE and maximum_gap is not None:
        raise ValueError("max_gap must be null when gap_policy is none.")
    if maximum_gap is not None and maximum_gap <= 0:
        raise ValueError("max_gap must be a positive integer.")


def _require_explicit_features_unique(
    feature_columns: list[str] | str,
    exclude_columns: Sequence[str],
) -> None:
    """Reject duplicate features and features that are also excluded.

    Args:
        feature_columns: ``auto`` or an explicit allowlist.
        exclude_columns: Columns that must not be read as features.

    Raises:
        ValueError: The allowlist repeats a name or overlaps the exclude list.
    """
    if feature_columns == "auto":
        return
    if len(feature_columns) != len(set(feature_columns)):
        raise ValueError("feature_columns contains a duplicate.")
    _overlap_message(
        feature_columns,
        exclude_columns,
        "A column cannot be both a feature and excluded",
    )


def _require_ratio_split(train_ratio: float, validation_ratio: float, test_ratio: float) -> None:
    """Require three positive ratios that sum to one.

    Args:
        train_ratio: Share of groups assigned to train.
        validation_ratio: Share of groups assigned to validation.
        test_ratio: Share of groups assigned to the final test.

    Raises:
        ValueError: A ratio is outside (0, 1) or the three ratios do not sum to 1.
    """
    ratios = {
        "train_ratio": train_ratio,
        "validation_ratio": validation_ratio,
        "test_ratio": test_ratio,
    }
    for name, ratio in ratios.items():
        if not 0 < ratio < 1:
            raise ValueError(f"{name} must be between 0 and 1.")
    total = train_ratio + validation_ratio + test_ratio
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError(f"Split ratios must sum to 1. They sum to {total}.")


def _require_percentile_pair(percentiles: tuple[float, float]) -> None:
    """Require a low and high percentile in unit interval order.

    Args:
        percentiles: Inclusive clip percentiles on a 0 to 100 scale.

    Raises:
        ValueError: The pair is out of range or inverted.
    """
    low, high = percentiles
    if not 0 <= low < high <= 100:
        raise ValueError("clip_percentiles must satisfy 0 <= low < high <= 100.")


def _require_table_path(path: Path) -> Path:
    """Require a CSV or Parquet suffix.

    Args:
        path: Configured table path.

    Returns:
        The same path.

    Raises:
        ValueError: The suffix is not supported. The file is not opened.
    """
    if table_suffix_is_supported(path):
        return path
    raise ValueError(f"Table files must end in .csv or .parquet, got {path.name}.")


class ProjectConfig(StrictConfigModel):
    """Names and seeds the run.

    Attributes:
        name: Short project name written into the report.
        seed: Seed for any sampling the later pipeline is allowed to do.
        notes: Free text stored with the run. Do not put secrets here.
    """

    name: Annotated[str, Field(min_length=1)]
    seed: Annotated[int, Field(ge=0)] = 7
    notes: str = ""


class ConnectorConfig(StrictConfigModel):
    """File paths for the three logical tables.

    Only ``files`` is accepted. Warehouse connectors are out of scope.

    Attributes:
        type: Connector kind. Must be ``files``.
        assets: CSV or Parquet path for the asset table.
        signals: CSV or Parquet path for the signal table.
        events: CSV or Parquet path for the event table.
    """

    type: Annotated[str, Field(pattern=r"(?i)files")] = "files"
    assets: Path
    signals: Path
    events: Path

    @model_validator(mode="before")
    @classmethod
    def reject_warehouse_connector(cls, value: object) -> object:
        """Reject every connector other than local files.

        Args:
            value: Raw connector mapping.

        Returns:
            The original value when it is files-only or not a mapping.

        Raises:
            ValueError: The connector type is not ``files``.
        """
        mapping = _string_key_mapping(value)
        if mapping is None:
            return value
        raw_type = mapping.get("type", "files")
        if isinstance(raw_type, str) and raw_type.strip().casefold() != "files":
            raise ValueError(
                f"Connector {raw_type!r} is not available. This package reads CSV and Parquet only."
            )
        return value

    @field_validator("assets", "signals", "events")
    @classmethod
    def require_csv_or_parquet(cls, path: Path) -> Path:
        """Reject table paths that are not CSV or Parquet.

        Args:
            path: One of the three table paths.

        Returns:
            The same path when the suffix is supported.
        """
        return _require_table_path(path)


class AssetsConfig(StrictConfigModel):
    """How to read the asset table.

    Attributes:
        id_column: Column that identifies an asset. It is never a feature.
        extra_columns: Static columns explicitly allowlisted as features.
    """

    id_column: Annotated[str, Field(min_length=1)]
    extra_columns: list[str] = Field(default_factory=list)

    @field_validator("extra_columns")
    @classmethod
    def reject_duplicate_extra_columns(cls, columns: list[str]) -> list[str]:
        """Reject a repeated static column.

        Args:
            columns: Allowlisted static columns.

        Returns:
            The same list when every name is unique and non-empty.

        Raises:
            ValueError: A name is blank or repeated.
        """
        if any(not column.strip() for column in columns):
            raise ValueError("extra_columns cannot contain an empty name.")
        if len(columns) != len(set(columns)):
            raise ValueError("extra_columns contains a duplicate.")
        return columns


class SignalsConfig(StrictConfigModel):
    """How to read the signal panel and which columns may become features.

    ``available_at_column`` null means delayed-record leakage is ``NOT_CHECKED``,
    not passed. ``feature_columns: auto`` is stored unresolved.

    Attributes:
        id_column: Asset identifier column on the signal file.
        event_time_column: Column of the time the reading happened.
        available_at_column: Column of the time the reading became knowable.
        timestamp_type: Comparison unit for the time columns.
        feature_columns: Explicit allowlist, or ``auto``.
        exclude_columns: Columns dropped even when ``feature_columns`` is ``auto``.
        frequency: Reserved resampling hint. Null means no resampling.
        gap_policy: ``none`` or bounded ``ffill``.
        max_gap: Largest forward fill, required only for ``ffill``.
    """

    id_column: Annotated[str, Field(min_length=1)]
    event_time_column: Annotated[str, Field(min_length=1)]
    available_at_column: str | None = None
    timestamp_type: TimestampType
    feature_columns: Annotated[list[str] | str, BeforeValidator(_parse_feature_columns)] = "auto"
    exclude_columns: list[str] = Field(default_factory=list)
    frequency: str | None = None
    gap_policy: Annotated[GapPolicy, BeforeValidator(_parse_gap_policy_value)] = GapPolicy.NONE
    max_gap: int | None = None

    @model_validator(mode="after")
    def check_signals(self) -> "SignalsConfig":
        """Check gap settings and the explicit allowlist.

        Returns:
            This configuration when the signal rules hold.
        """
        _require_consistent_gap(self.gap_policy, self.max_gap)
        _require_explicit_features_unique(self.feature_columns, self.exclude_columns)
        if self.feature_columns != "auto" and len(self.feature_columns) == 0:
            raise ValueError("feature_columns must be 'auto' or a non-empty list.")
        if self.frequency is not None and not self.frequency.strip():
            raise ValueError("frequency must be null or a non-empty string.")
        return self


class EventsConfig(StrictConfigModel):
    """How to read events, and which types are terminal versus competing.

    A repair, a warranty claim, a fault code, and a roadside breakdown are
    different events. Only ``terminal_types`` define the question.

    Attributes:
        id_column: Asset identifier column on the event file.
        event_time_column: Column of the time the event happened.
        available_at_column: Column of the time the event became knowable.
        type_column: Column that names the event type.
        terminal_types: Event types that answer the prediction question.
        competing_types: Closes that are not silent negatives, such as exit.
        forbidden_as_features: Event columns that describe the event itself.
    """

    id_column: Annotated[str, Field(min_length=1)]
    event_time_column: Annotated[str, Field(min_length=1)]
    available_at_column: str | None = None
    type_column: Annotated[str, Field(min_length=1)]
    terminal_types: Annotated[list[str], Field(min_length=1)]
    competing_types: list[str] = Field(default_factory=list)
    forbidden_as_features: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_event_types(self) -> "EventsConfig":
        """Keep terminal types disjoint from competing types.

        Returns:
            This configuration when the event types are usable.
        """
        _overlap_message(
            self.terminal_types,
            self.competing_types,
            "An event type cannot be both terminal and competing",
        )
        _require_no_duplicate_strings(self.terminal_types, "terminal_types")
        _require_no_duplicate_strings(self.competing_types, "competing_types")
        _require_no_duplicate_strings(self.forbidden_as_features, "forbidden_as_features")
        return self


def _require_no_duplicate_strings(names: Sequence[str], label: str) -> None:
    """Reject a blank or repeated string in a name list.

    Args:
        names: Configured names.
        label: Field name used in the error.

    Raises:
        ValueError: A name is blank or repeated, ignoring case.
    """
    if any(not name.strip() for name in names):
        raise ValueError(f"{label} cannot contain an empty name.")
    folded = [name.casefold() for name in names]
    if len(folded) != len(set(folded)):
        raise ValueError(f"{label} contains a duplicate.")


class ContractConfig(StrictConfigModel):
    """Episode bounds and the replacement rule.

    Attributes:
        observation_start_column: Optional column for episode start.
        observation_end_column: Optional column for episode end.
        replacement_starts_new_episode: When true, windows cannot cross a replacement.
        replacement_types: Event types that close the current episode.
    """

    observation_start_column: str | None = None
    observation_end_column: str | None = None
    replacement_starts_new_episode: bool = True
    replacement_types: list[str] = Field(default_factory=list)

    @field_validator("replacement_types")
    @classmethod
    def reject_duplicate_replacements(cls, names: list[str]) -> list[str]:
        """Reject a blank or repeated replacement type.

        Args:
            names: Replacement event types.

        Returns:
            The same list when it is well formed.
        """
        _require_no_duplicate_strings(names, "replacement_types")
        return names


class LabelingConfig(StrictConfigModel):
    """The v0.1 question: remaining useful life on a completed trajectory.

    ``censored_policy`` ``reject`` stops the run with an error when a censored
    or unsupported history is present. ``report`` leaves that history out of
    every split, continues, and names it in the report. Neither policy drops
    the history quietly. ``unknown_policy: exclude_from_loss`` is the old
    silent-exclusion setting and is rejected.

    Attributes:
        task: Completed-trajectory RUL, or the C-MAPSS last-observation adapter.
        horizon: Unused by the v0.1 tasks. A positive value is stored and not applied.
        unit: Unit of time written into the report.
        censored_policy: ``reject`` or ``report`` for histories v0.1 cannot score.
    """

    task: Annotated[LabelTask, BeforeValidator(_parse_label_task)] = (
        LabelTask.COMPLETED_TRAJECTORY_RUL
    )
    horizon: int | None = None
    unit: TimeUnit
    censored_policy: CensoredHistoryPolicy = CensoredHistoryPolicy.REJECT

    @model_validator(mode="before")
    @classmethod
    def reject_silent_history_policy(cls, value: object) -> object:
        """Reject policies that would drop censored histories without a finding.

        Args:
            value: Raw labeling mapping.

        Returns:
            The original value when the policy is explicit.

        Raises:
            ValueError: The configuration uses the old field or a drop policy.
        """
        mapping = _string_key_mapping(value)
        if mapping is None:
            return value
        if "unknown_policy" in mapping:
            raise ValueError(
                "unknown_policy is not a v0.1 field. Set censored_policy to reject or report. "
                "Censored and unsupported histories are never dropped silently."
            )
        raw_policy = mapping.get("censored_policy", "reject")
        if isinstance(raw_policy, str) and raw_policy.strip().casefold() in _SILENT_CENSOR_POLICIES:
            raise ValueError(
                f"censored_policy {raw_policy!r} would hide histories. Use reject or report."
            )
        return value

    @model_validator(mode="after")
    def check_horizon(self) -> "LabelingConfig":
        """Reject a non-positive horizon when one is set.

        Returns:
            This configuration when the optional horizon is usable.
        """
        if self.horizon is not None and self.horizon <= 0:
            raise ValueError("horizon must be a positive integer when it is set.")
        return self


class WindowsConfig(StrictConfigModel):
    """Lookback windows used to build features and labels.

    Attributes:
        lookback: Number of past steps visible at a prediction time.
        stride: Step between successive prediction times.
        discard_straddle_split: Drop windows whose lookback or label crosses a split.
    """

    lookback: Annotated[int, Field(gt=0)]
    stride: Annotated[int, Field(gt=0)] = 1
    discard_straddle_split: bool = True


class OfficialPartitionsConfig(StrictConfigModel):
    """Publisher-defined membership files. The ids are not reshuffled.

    Attributes:
        train_ids: File of training entity ids.
        validation_ids: File of validation entity ids.
        test_ids: File of final-test entity ids.
    """

    train_ids: Path
    validation_ids: Path
    test_ids: Path

    @model_validator(mode="after")
    def check_distinct_files(self) -> "OfficialPartitionsConfig":
        """Require three different id files.

        Returns:
            This configuration when the paths differ.
        """
        rendered = (
            self.train_ids.as_posix(),
            self.validation_ids.as_posix(),
            self.test_ids.as_posix(),
        )
        if len(set(rendered)) != len(rendered):
            raise ValueError("official partition id files must be distinct.")
        return self


class GroupHoldoutConfig(StrictConfigModel):
    """Assign whole groups to one split each.

    Attributes:
        group_column: Column that defines a group, usually the asset id.
        train_ratio: Share of groups in train.
        validation_ratio: Share of groups in validation.
        test_ratio: Share of groups in the final test.
    """

    group_column: Annotated[str, Field(min_length=1)]
    train_ratio: float
    validation_ratio: float
    test_ratio: float

    @model_validator(mode="after")
    def check_ratios(self) -> "GroupHoldoutConfig":
        """Require positive ratios that sum to one.

        Returns:
            This configuration when the ratios form a split.
        """
        _require_ratio_split(self.train_ratio, self.validation_ratio, self.test_ratio)
        return self


# One-asset validation and test splits are warned, not treated as a full holdout.
# The synthetic demo has one asset in each of those splits, so it records this warning.
DEFAULT_MIN_ASSETS_PER_SPLIT = 3


class SplitConfig(StrictConfigModel):
    """Which named protocol builds the three splits.

    ``random`` is rejected. ``global_time`` is deferred to v0.2. Only the block
    for the selected protocol may be set.

    Attributes:
        protocol: Named split protocol.
        official_partitions: Id files for ``official_partitions``.
        group_holdout: Ratios for ``group_holdout``.
        min_assets_per_split: Smallest split that is not listed in report
            ``risks``. The default of 3 applies to train, validation, and test.
            A validation or test split with fewer assets still receives scores
            when it has rows. An empty split is ``NOT_COMPUTED`` and the risk
            says so.
    """

    protocol: Annotated[SplitProtocol, BeforeValidator(_parse_protocol_value)]
    official_partitions: OfficialPartitionsConfig | None = None
    group_holdout: GroupHoldoutConfig | None = None
    min_assets_per_split: Annotated[int, Field(ge=1)] = DEFAULT_MIN_ASSETS_PER_SPLIT

    @model_validator(mode="before")
    @classmethod
    def reject_split_type_key(cls, value: object) -> object:
        """Reject ``global_time`` and the legacy ``type`` key.

        Args:
            value: Raw split mapping.

        Returns:
            The original value when it is a v0.1 split.

        Raises:
            ValueError: ``global_time`` or ``split.type`` is present.
        """
        mapping = _string_key_mapping(value)
        if mapping is None:
            return value
        protocol = mapping.get("protocol")
        if isinstance(protocol, str) and protocol.strip().casefold() == "global_time":
            raise ValueError(_GLOBAL_TIME_DEFERRED)
        if "global_time" in mapping:
            raise ValueError(_GLOBAL_TIME_DEFERRED)
        if "type" not in mapping:
            return value
        raw_type = mapping["type"]
        if isinstance(raw_type, str):
            if raw_type.strip().casefold() == "global_time":
                raise ValueError(_GLOBAL_TIME_DEFERRED)
            try:
                reject_random_split(raw_type)
            except ConfigurationError as error:
                raise ValueError(str(error)) from error
        raise ValueError(
            "Use split.protocol, not split.type. "
            "v0.1 accepts official_partitions and group_holdout. "
            "global_time is deferred to v0.2."
        )

    @model_validator(mode="after")
    def check_protocol_block(self) -> "SplitConfig":
        """Require the settings block that matches the protocol and no other block.

        Returns:
            This configuration when exactly one matching block is present.
        """
        blocks = {
            SplitProtocol.OFFICIAL_PARTITIONS: self.official_partitions,
            SplitProtocol.GROUP_HOLDOUT: self.group_holdout,
        }
        if blocks[self.protocol] is None:
            raise ValueError(
                f"split.protocol {self.protocol.value} requires its {self.protocol.value} block."
            )
        extra_blocks = [
            protocol.value
            for protocol, block in blocks.items()
            if block is not None and protocol is not self.protocol
        ]
        if extra_blocks:
            joined = ", ".join(extra_blocks)
            raise ValueError(
                f"Only the settings block for the selected protocol may be set. Remove: {joined}."
            )
        return self


class PreprocessingConfig(StrictConfigModel):
    """Train-only clip and scale settings.

    Attributes:
        clip_percentiles: Inclusive low and high percentiles, fit on train only.
        scaler: Scaler name, fit on train only.
    """

    clip_percentiles: tuple[float, float] = (1.0, 99.0)
    scaler: ScalerName = ScalerName.STANDARD

    @field_validator("clip_percentiles")
    @classmethod
    def check_percentiles(cls, percentiles: tuple[float, float]) -> tuple[float, float]:
        """Reject an inverted or out-of-range percentile pair.

        Args:
            percentiles: Low and high clip percentiles.

        Returns:
            The same pair when it is ordered inside 0 to 100.
        """
        _require_percentile_pair(percentiles)
        return percentiles


class LeakageConfig(StrictConfigModel):
    """Which checks abort a run, and which checks only warn.

    A check listed in neither sequence is not a pass. Once the suite exists,
    an omitted check is reported as ``NOT_CHECKED``.

    Attributes:
        fail_on: Checks that abort training when their status is ``CONFIRMED``.
        warn_on: Checks that are reported and do not abort by themselves.
        association_warn_threshold: Train-only association level that warns.
    """

    fail_on: Annotated[list[LeakageCheckId], Field(min_length=1)]
    warn_on: list[LeakageCheckId] = Field(default_factory=list)
    association_warn_threshold: Annotated[float, Field(gt=0, le=1)] = 0.85

    @model_validator(mode="after")
    def check_check_lists(self) -> "LeakageConfig":
        """Keep fail and warn lists unique and disjoint.

        Returns:
            This configuration when every check is classified once.
        """
        _require_unique(self.fail_on, "fail_on check")
        _require_unique(self.warn_on, "warn_on check")
        overlap = set(self.fail_on) & set(self.warn_on)
        if overlap:
            names = ", ".join(sorted(item.value for item in overlap))
            raise ValueError(f"A check cannot be both fail_on and warn_on: {names}.")
        return self


class ModelsConfig(StrictConfigModel):
    """Baselines to fit.

    v0.1 fits a training-constant model and one histogram gradient boosting
    model. Persistence is rejected. Age and logistic regression are not in v0.1.

    Attributes:
        include: Baseline names in report order.
    """

    include: Annotated[
        list[Annotated[BaselineName, BeforeValidator(_parse_baseline_value)]],
        Field(min_length=1),
    ]

    @field_validator("include")
    @classmethod
    def reject_duplicate_baselines(cls, include: list[BaselineName]) -> list[BaselineName]:
        """Reject a repeated baseline.

        Args:
            include: Requested baselines.

        Returns:
            The same list when each baseline appears once.
        """
        _require_unique(include, "baseline")
        return include


class EvaluationConfig(StrictConfigModel):
    """Where the headline model is chosen, and which plots are requested.

    v0.1 chooses the headline model on validation and scores the final test
    once. An alert block is rejected. Alerts are deferred to v0.2.

    Attributes:
        threshold_split: Must be validation. v0.1 uses this as the choice split.
        report_split_order: Train, validation, and test, each once.
        plots: Plot names to include once plotting exists.
    """

    threshold_split: Annotated[str, BeforeValidator(_parse_threshold_split)] = "validation"
    report_split_order: list[SplitReportName] = Field(
        default_factory=lambda: [
            SplitReportName.TRAIN,
            SplitReportName.VALIDATION,
            SplitReportName.TEST,
        ]
    )
    plots: list[PlotName] = Field(
        default_factory=lambda: [
            PlotName.PREDICTION_ERROR,
            PlotName.ERROR_BY_UNIT,
            PlotName.HISTORY_DISPOSITIONS,
        ]
    )

    @field_validator("report_split_order")
    @classmethod
    def check_split_order(cls, order: list[SplitReportName]) -> list[SplitReportName]:
        """Require each split exactly once.

        Args:
            order: Requested report order.

        Returns:
            The same order when it is a permutation of the three splits.
        """
        if set(order) != _REPORT_SPLITS or len(order) != len(_REPORT_SPLITS):
            raise ValueError("report_split_order must list train, validation, and test once each.")
        return order

    @field_validator("plots")
    @classmethod
    def reject_duplicate_plots(cls, plots: list[PlotName]) -> list[PlotName]:
        """Reject a repeated plot name.

        Args:
            plots: Requested plots.

        Returns:
            The same list when each plot appears once.
        """
        _require_unique(plots, "plot")
        return plots

    @model_validator(mode="before")
    @classmethod
    def reject_alerts(cls, value: object) -> object:
        """Reject alert settings. They are deferred to v0.2.

        Args:
            value: Raw evaluation mapping.

        Returns:
            The original value when it does not request alerts.

        Raises:
            ValueError: An alert block or an alert plot is present.
        """
        mapping = _string_key_mapping(value)
        if mapping is None:
            return value
        if "alert" in mapping or "alerts" in mapping:
            raise ValueError(_ALERTS_DEFERRED)
        plots = mapping.get("plots")
        if isinstance(plots, list):
            for plot_name in plots:
                if isinstance(plot_name, str) and plot_name.strip().casefold() in _ALERT_PLOT_NAMES:
                    raise ValueError(_ALERTS_DEFERRED)
        return value


class ReportConfig(StrictConfigModel):
    """Where the run writes HTML and JSON.

    Attributes:
        formats: At least ``html`` and ``json``. ``markdown`` is optional.
        title: Report title.
        output_dir: Directory under which ``rulsafe-runs/<run_id>/`` is created.
    """

    formats: Annotated[list[ReportFormat], Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    output_dir: Path = Path("rulsafe-runs")

    @field_validator("formats")
    @classmethod
    def require_html_and_json(cls, formats: list[ReportFormat]) -> list[ReportFormat]:
        """Require the two formats the report contract always writes.

        Args:
            formats: Requested formats.

        Returns:
            The same list when HTML and JSON are both present once.
        """
        _require_unique(formats, "report format")
        missing = _REQUIRED_REPORT_FORMATS - set(formats)
        if missing:
            names = ", ".join(sorted(item.value for item in missing))
            raise ValueError(f"report.formats must include {names}.")
        return formats


class RunConfig(StrictConfigModel):
    """Complete configuration for one pre-training check.

    Build one with :meth:`from_mapping` or with :func:`rulsafe.load_config`.

    Attributes:
        project: Name, seed, and notes.
        connector: Local file paths.
        assets: Asset-table mapping.
        signals: Signal-table mapping and feature allowlist.
        events: Event-table mapping and terminal-event definition.
        contract: Episode bounds and replacement rule.
        labeling: Question, horizon, and censored-row policy.
        windows: Lookback and stride.
        split: Named protocol and its settings.
        preprocessing: Train-only clip and scale settings.
        leakage: Fail and warn checks.
        models: Baselines to fit.
        evaluation: Validation choices and plots. Alerts are deferred to v0.2.
        report: Output formats and directory.
    """

    project: ProjectConfig
    connector: ConnectorConfig
    assets: AssetsConfig
    signals: SignalsConfig
    events: EventsConfig
    contract: ContractConfig
    labeling: LabelingConfig
    windows: WindowsConfig
    split: SplitConfig
    preprocessing: PreprocessingConfig
    leakage: LeakageConfig
    models: ModelsConfig
    evaluation: EvaluationConfig
    report: ReportConfig

    @model_validator(mode="before")
    @classmethod
    def reject_top_level_alerts(cls, value: object) -> object:
        """Reject a top-level alerts block. Alerts are deferred to v0.2.

        Args:
            value: Raw configuration mapping.

        Returns:
            The original value when alerts were not requested.

        Raises:
            ValueError: ``alert`` or ``alerts`` is present.
        """
        mapping = _string_key_mapping(value)
        if mapping is not None and ("alert" in mapping or "alerts" in mapping):
            raise ValueError(_ALERTS_DEFERRED)
        return value

    @model_validator(mode="after")
    def check_cross_fields(self) -> "RunConfig":
        """Check rules that span more than one configuration block.

        Returns:
            This configuration when the blocks agree.
        """
        _require_allowlist_is_safe(self)
        _overlap_message(
            self.events.terminal_types,
            self.contract.replacement_types,
            "An event type cannot be both terminal and a replacement",
        )
        return self

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "RunConfig":
        """Validate a configuration mapping.

        Args:
            mapping: Configuration objects, usually parsed from YAML.

        Returns:
            The validated configuration.

        Raises:
            ConfigurationError: The value is not a mapping or fails the schema.
        """
        if not isinstance(mapping, Mapping):
            raise ConfigurationError("Configuration must be a mapping.")
        try:
            return cls.model_validate(dict(mapping))
        except ValidationError as error:
            raise ConfigurationError(str(error)) from error


def _explicit_feature_names(config: RunConfig) -> list[str]:
    """Return feature names that are already explicit in the configuration.

    Args:
        config: Validated configuration being checked.

    Returns:
        Static allowlist columns plus signal features when those are not ``auto``.
    """
    names = list(config.assets.extra_columns)
    if isinstance(config.signals.feature_columns, list):
        names.extend(config.signals.feature_columns)
    return names


def _require_allowlist_is_safe(config: RunConfig) -> None:
    """Reject identifiers, target names, and event metadata on the allowlist.

    Args:
        config: Configuration being checked.

    Raises:
        ValueError: An explicit feature is not allowed on the allowlist.
    """
    identifier_names = {
        config.assets.id_column.casefold(),
        config.signals.id_column.casefold(),
        config.events.id_column.casefold(),
    }
    forbidden = _folded(config.events.forbidden_as_features)
    for column_name in _explicit_feature_names(config):
        folded = column_name.casefold()
        if folded in identifier_names or column_is_identifier(column_name, config.assets.id_column):
            raise ValueError(f"Identifier column {column_name!r} cannot be a feature.")
        if column_is_target_name(column_name):
            raise ValueError(f"Target column {column_name!r} cannot be a feature.")
        if folded in forbidden:
            raise ValueError(f"Event metadata column {column_name!r} cannot be a feature.")


__all__ = [
    "DEFAULT_FAIL_ON_CHECKS",
    "DEFAULT_WARN_ON_CHECKS",
    "AssetsConfig",
    "BaselineName",
    "CensoredHistoryPolicy",
    "ConnectorConfig",
    "ContractConfig",
    "EvaluationConfig",
    "EventsConfig",
    "GroupHoldoutConfig",
    "LabelTask",
    "LabelingConfig",
    "LeakageCheckId",
    "LeakageConfig",
    "LeakageStatus",
    "ModelsConfig",
    "OfficialPartitionsConfig",
    "PlotName",
    "PreprocessingConfig",
    "ProjectConfig",
    "ReportConfig",
    "ReportFormat",
    "RunConfig",
    "ScalerName",
    "SignalsConfig",
    "SplitConfig",
    "SplitProtocol",
    "SplitReportName",
    "StrictConfigModel",
    "TimeUnit",
    "WindowsConfig",
]
