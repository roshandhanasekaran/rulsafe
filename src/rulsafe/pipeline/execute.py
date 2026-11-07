"""Run a completed-trajectory check for group holdout and CSV inputs.

The histogram gradient boosting baseline is recorded as ``NOT_COMPUTED``.
The constant baseline is fit on training targets only. Censored and
unsupported assets stay in the report.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from rulsafe.config import LeakageCheckId, LeakageStatus, RunConfig, SplitProtocol
from rulsafe.contract import LogicalTableRole
from rulsafe.eval.metrics import MetricsReport, SplitMetrics
from rulsafe.exceptions import ConfigurationError
from rulsafe.io.files import load_table
from rulsafe.leakage.checks import LeakageFinding
from rulsafe.leakage.report import with_documented_coverage
from rulsafe.leakage.suite import LeakageSuiteResult
from rulsafe.mapping import LogicalTables
from rulsafe.models.baselines import FittedBaseline, fit_constant_baseline
from rulsafe.pipeline.episodes import Episode, build_episodes
from rulsafe.pipeline.features import build_causal_features
from rulsafe.pipeline.labels import HistorySupport, assign_remaining_life
from rulsafe.pipeline.split import SplitName, assign_splits
from rulsafe.report.json import MetricValue


def execute_group_holdout(
    config: RunConfig, output_directory: Path
) -> tuple[
    LeakageSuiteResult,
    MetricsReport,
    dict[str, object],
]:
    """Run the implemented slice and build the JSON document.

    Args:
        config: Validated configuration. The protocol must be group holdout.
        output_directory: Directory for ``report.json``.

    Returns:
        The leakage result, metrics, and the JSON-ready document.

    Raises:
        ConfigurationError: The files or the protocol cannot be used for this slice.
        ContractError: A censored history was configured to be rejected.
    """
    holdout = config.split.group_holdout
    if config.split.protocol is not SplitProtocol.GROUP_HOLDOUT or holdout is None:
        raise ConfigurationError(
            "This run implements group_holdout on CSV files. "
            "official_partitions and cmapss are not implemented yet."
        )
    tables = LogicalTables(
        assets=load_table(Path(config.connector.assets), LogicalTableRole.ASSETS),
        signals=load_table(Path(config.connector.signals), LogicalTableRole.SIGNALS),
        events=load_table(Path(config.connector.events), LogicalTableRole.EVENTS),
    )
    episodes = build_episodes(tables, config)
    labeled = _labeled_rows(episodes, config)
    split = assign_splits(
        config.split.protocol,
        group_identifiers=tuple(episode.asset_id for episode in episodes),
        train_ratio=holdout.train_ratio,
        validation_ratio=holdout.validation_ratio,
        test_ratio=holdout.test_ratio,
        seed=config.project.seed,
    )
    training_targets = [
        _number(row["remaining_life"])
        for row in labeled
        if row["asset_id"] in set(split[SplitName.TRAIN]) and row["remaining_life"] is not None
    ]
    constant = fit_constant_baseline(training_targets=training_targets)
    metrics = _metrics_report(labeled, split, constant)
    censored_ids = tuple(
        episode.asset_id
        for episode in episodes
        if episode.support in {HistorySupport.CENSORED, HistorySupport.UNSUPPORTED}
    )
    findings = with_documented_coverage(
        (
            _unsupported_history_finding(censored_ids),
            _future_feature_finding(episodes, config),
            _random_split_finding(config),
        )
    )
    leakage = LeakageSuiteResult(findings=findings)
    document = _document(config, episodes, split, censored_ids, leakage, metrics, constant)
    output_directory.mkdir(parents=True, exist_ok=True)
    report_path = output_directory / "report.json"
    document["report_json"] = str(report_path)
    report_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return leakage, metrics, document


def _labeled_rows(episodes: Sequence[Episode], config: RunConfig) -> list[dict[str, object]]:
    """Build one supervised or reported row per causal prediction time.

    Args:
        episodes: Classified asset histories.
        config: Feature and label settings.

    Returns:
        Rows with asset id, remaining life or None, and causal features.
    """
    feature_columns = config.signals.feature_columns
    if not isinstance(feature_columns, list):
        raise ConfigurationError("feature_columns: auto is not resolved in this run yet.")
    rows: list[dict[str, object]] = []
    for episode in episodes:
        for prediction_time in _prediction_times(episode):
            remaining = assign_remaining_life(
                support=episode.support,
                policy=config.labeling.censored_policy,
                prediction_time=prediction_time,
                episode_end=episode.end_time,
            )
            features = build_causal_features(
                rows=episode.rows,
                prediction_time=prediction_time,
                gap_policy=config.signals.gap_policy,
                maximum_gap=config.signals.max_gap,
                feature_columns=feature_columns,
            )
            rows.append(
                {
                    "asset_id": episode.asset_id,
                    "prediction_time": prediction_time,
                    "remaining_life": remaining,
                    "features": features,
                }
            )
    return rows


def _prediction_times(episode: Episode) -> tuple[float, ...]:
    """Return signal times strictly before the episode end.

    Args:
        episode: One asset history.

    Returns:
        Sorted unique prediction times. An open unsupported history uses every
        signal time.
    """
    times = {
        _number(row["event_time"])
        for row in episode.rows
        if _before_end(_number(row["event_time"]), episode.end_time)
    }
    return tuple(sorted(times))


def _before_end(event_time: float, end_time: float | None) -> bool:
    """Return whether a signal time is a valid prediction time.

    Args:
        event_time: Signal time.
        end_time: Episode end, or None when the history has no close.

    Returns:
        True when the time is strictly before the end, or when there is no end.
    """
    if end_time is None:
        return True
    return event_time < end_time


def _metrics_report(
    labeled: Sequence[Mapping[str, object]],
    split: Mapping[SplitName, tuple[str, ...]],
    constant: FittedBaseline,
) -> MetricsReport:
    """Score the constant baseline. The tree model is not computed.

    Args:
        labeled: Prediction rows.
        split: Asset ids by split.
        constant: Model fit on the training split only.

    Returns:
        Validation and final-test metrics.
    """
    return MetricsReport(
        validation=_split_metrics(labeled, split[SplitName.VALIDATION], constant),
        test=_split_metrics(labeled, split[SplitName.TEST], constant),
    )


def _split_metrics(
    labeled: Sequence[Mapping[str, object]],
    asset_ids: tuple[str, ...],
    constant: FittedBaseline,
) -> SplitMetrics:
    """Score one split.

    Args:
        labeled: Prediction rows.
        asset_ids: Assets in this split.
        constant: Training-only constant model.

    Returns:
        Computed root-mean-square error, or ``NOT_COMPUTED`` when the split
        has no scored rows. The tree metric is always ``NOT_COMPUTED``.
    """
    actual = [
        _number(row["remaining_life"])
        for row in labeled
        if row["asset_id"] in asset_ids and row["remaining_life"] is not None
    ]
    if constant.constant_value is None or not actual:
        constant_metric = MetricValue.not_computed()
    else:
        squared = [(constant.constant_value - value) ** 2 for value in actual]
        constant_metric = MetricValue.computed((sum(squared) / len(squared)) ** 0.5)
    return SplitMetrics(
        values={
            "constant_root_mean_square_error": constant_metric,
            "hist_gradient_boosting_root_mean_square_error": MetricValue.not_computed(),
        }
    )


def _unsupported_history_finding(censored_ids: tuple[str, ...]) -> LeakageFinding:
    """Report censored assets instead of dropping them.

    Args:
        censored_ids: Assets that were not scored.

    Returns:
        A pass when every such asset is named, which this function always does.
    """
    if censored_ids:
        listed = ", ".join(censored_ids)
        evidence = f"Censored or unsupported assets were kept in the report: {listed}."
    else:
        evidence = "No censored or unsupported assets were present."
    return LeakageFinding(
        check_id=LeakageCheckId.UNSUPPORTED_HISTORY,
        status=LeakageStatus.PASS,
        evidence=evidence,
        remedy="Keep reject or report. Do not drop these histories.",
    )


def _future_feature_finding(episodes: Sequence[Episode], config: RunConfig) -> LeakageFinding:
    """Confirm features at time t ignore rows that were not yet knowable.

    Args:
        episodes: Histories whose rows may include later records.
        config: Feature settings.

    Returns:
        Pass when dropping future rows leaves the features unchanged.
    """
    feature_columns = config.signals.feature_columns
    if not isinstance(feature_columns, list):
        raise ConfigurationError("feature_columns: auto is not resolved in this run yet.")
    for episode in episodes:
        for prediction_time in _prediction_times(episode):
            full = build_causal_features(
                rows=episode.rows,
                prediction_time=prediction_time,
                gap_policy=config.signals.gap_policy,
                maximum_gap=config.signals.max_gap,
                feature_columns=feature_columns,
            )
            past_rows = tuple(
                row
                for row in episode.rows
                if _number(row["event_time"]) <= prediction_time
                and _number(row["available_at"]) <= prediction_time
            )
            past = build_causal_features(
                rows=past_rows,
                prediction_time=prediction_time,
                gap_policy=config.signals.gap_policy,
                maximum_gap=config.signals.max_gap,
                feature_columns=feature_columns,
            )
            if full != past:
                return LeakageFinding(
                    check_id=LeakageCheckId.FUTURE_IN_FEATURES,
                    status=LeakageStatus.CONFIRMED,
                    evidence=(
                        f"Features for {episode.asset_id} at {prediction_time} "
                        "changed when later rows were removed."
                    ),
                    remedy="Use only rows with event_time and available_at at or before t.",
                )
    return LeakageFinding(
        check_id=LeakageCheckId.FUTURE_IN_FEATURES,
        status=LeakageStatus.PASS,
        evidence="Features at each prediction time ignore rows that were not yet knowable.",
        remedy="Keep the causal filter.",
    )


def _random_split_finding(config: RunConfig) -> LeakageFinding:
    """Record that this run did not use a random split.

    Args:
        config: Validated configuration.

    Returns:
        A pass. ``random`` and ``global_time`` are rejected before a run starts.
    """
    return LeakageFinding(
        check_id=LeakageCheckId.RANDOM_SPLIT,
        status=LeakageStatus.PASS,
        evidence=f"Split protocol is {config.split.protocol.value}.",
        remedy="Keep a named protocol. Do not shuffle panel rows.",
    )


def _number(value: object) -> float:
    """Convert a stored cell to a float.

    Args:
        value: Numeric cell.

    Returns:
        The float value.

    Raises:
        ConfigurationError: The cell is not numeric.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ConfigurationError(f"Expected a number, got {value!r}.")
    try:
        return float(value)
    except ValueError as error:
        raise ConfigurationError(f"Expected a number, got {value!r}.") from error


def _document(
    config: RunConfig,
    episodes: Sequence[Episode],
    split: Mapping[SplitName, tuple[str, ...]],
    censored_ids: tuple[str, ...],
    leakage: LeakageSuiteResult,
    metrics: MetricsReport,
    constant: FittedBaseline,
) -> dict[str, object]:
    """Build the JSON report body.

    Args:
        config: Validated configuration.
        episodes: Classified histories.
        split: Asset ids by split.
        censored_ids: Assets that were not scored.
        leakage: Audit rows, including documented coverage.
        metrics: Validation and test metrics.
        constant: Training-only constant model.

    Returns:
        A JSON-ready mapping.
    """
    return {
        "project": config.project.name,
        "disclaimer": (
            "Research software, not a safety-certified prognostic. "
            "A listed pass is not a guarantee that every leak was checked."
        ),
        "asset_count": len(episodes),
        "censored_or_unsupported_asset_ids": list(censored_ids),
        "dropped_asset_ids": [],
        "splits": {name.value: list(identifiers) for name, identifiers in split.items()},
        "constant_training_value": constant.constant_value,
        "constant_training_row_count": constant.training_row_count,
        "gap_policy": config.signals.gap_policy.value,
        "leakage": [
            {
                "check_id": finding.check_id.value,
                "status": finding.status.value,
                "evidence": finding.evidence,
                "remedy": finding.remedy,
            }
            for finding in leakage.findings
        ],
        "metrics": {
            "validation": {
                name: metric.to_dict() for name, metric in metrics.validation.values.items()
            },
            "test": {name: metric.to_dict() for name, metric in metrics.test.values.items()},
        },
        "headline_model": "constant",
        "tree_model_status": MetricValue.not_computed().status.value,
    }
