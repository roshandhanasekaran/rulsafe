"""Run a completed-trajectory check for CSV or Parquet inputs.

The constant baseline and the histogram gradient boosting baseline are fit
on training rows only. Early stopping uses the validation split when that
split has scored rows. ``censored_policy`` ``reject`` writes a partial report
with status ``FAILED`` and no metrics, then stops. ``report`` leaves those
histories out of every split, continues, and names them. Official partition
files are used as written and are not shuffled.
"""

import json
import warnings
from collections.abc import Mapping, Sequence
from pathlib import Path

from rulsafe.config import (
    BaselineName,
    LeakageCheckId,
    LeakageStatus,
    RunConfig,
    SplitProtocol,
)
from rulsafe.contract import LogicalTableRole
from rulsafe.eval.metrics import (
    METRIC_SUFFIXES,
    MetricsReport,
    SplitMetrics,
    choose_headline,
    score_named_errors,
)
from rulsafe.exceptions import ConfigurationError, ContractError
from rulsafe.io.files import load_table
from rulsafe.leakage.checks import LeakageFinding
from rulsafe.leakage.report import with_documented_coverage
from rulsafe.leakage.suite import LeakageSuiteResult
from rulsafe.mapping import LogicalTables
from rulsafe.models.baselines import (
    FIXED_ITERATION_CAP,
    FittedBaseline,
    fit_constant_baseline,
    fit_histogram_gradient_boosting,
)
from rulsafe.pipeline.episodes import Episode, build_episodes
from rulsafe.pipeline.features import build_causal_features
from rulsafe.pipeline.labels import (
    HistoryDisposition,
    HistorySupport,
    assign_remaining_life,
    disposition_for_history,
)
from rulsafe.pipeline.split import (
    SplitName,
    assign_official_partitions,
    assign_splits,
    read_split_ids,
    split_size_risks,
)
from rulsafe.report.json import MetricComputationStatus, MetricValue


def execute_configured_run(
    config: RunConfig, output_directory: Path
) -> tuple[
    LeakageSuiteResult,
    MetricsReport,
    dict[str, object],
]:
    """Run group holdout or official partitions and build the JSON document.

    Args:
        config: Validated configuration.
        output_directory: Directory for ``report.json``.

    Returns:
        The leakage result, metrics, and the JSON-ready document.

    Raises:
        ConfigurationError: The files or the protocol cannot be used.
        ContractError: ``censored_policy`` is ``reject`` and a censored or
            unsupported history is present. A partial report with status
            ``FAILED`` and no metrics is written first.
    """
    tables = LogicalTables(
        assets=load_table(Path(config.connector.assets), LogicalTableRole.ASSETS),
        signals=load_table(Path(config.connector.signals), LogicalTableRole.SIGNALS),
        events=load_table(Path(config.connector.events), LogicalTableRole.EVENTS),
    )
    config = _resolve_auto_features(config, tables.signals.rows)
    episodes = build_episodes(tables, config)
    supervised, excluded = _separate_training_histories(episodes, config)
    censored_ids = tuple(
        episode.asset_id
        for episode in episodes
        if episode.support in {HistorySupport.CENSORED, HistorySupport.UNSUPPORTED}
    )
    _stop_when_censored_histories_are_rejected(
        config,
        episodes,
        censored_ids,
        excluded,
        output_directory,
    )
    labeled = _labeled_rows(supervised, config)
    split = _assign_split(config, tuple(episode.asset_id for episode in supervised))
    minimum = config.split.min_assets_per_split
    risks: list[dict[str, object]] = list(split_size_risks(split, minimum=minimum))
    rows_by_split = {
        name: _completed_rows(labeled, identifiers) for name, identifiers in split.items()
    }
    training_rows = rows_by_split[SplitName.TRAIN]
    validation_rows = rows_by_split[SplitName.VALIDATION]
    if not training_rows:
        raise ContractError("The training split has no completed-trajectory target.")
    constant = fit_constant_baseline(training_targets=tuple(target for _, target in training_rows))
    tree_requested = BaselineName.HIST_GRADIENT_BOOSTING in config.models.include
    tree: FittedBaseline | None = None
    if tree_requested:
        tree = _fit_tree(training_rows, validation_rows, random_state=config.project.seed)
        if not validation_rows:
            risks.append(_early_stopping_risk(len(split[SplitName.VALIDATION]), minimum))
    for risk in risks:
        warnings.warn(str(risk["message"]), UserWarning, stacklevel=2)
    metrics = _metrics_report(
        rows_by_split, constant=constant, tree=tree, tree_requested=tree_requested
    )
    recorded = [
        finding
        for finding in (
            _unsupported_history_finding(censored_ids),
            _future_feature_finding(episodes, config),
            _random_split_finding(config),
            _backend_split_finding(tree),
        )
        if finding is not None
    ]
    leakage = LeakageSuiteResult(findings=with_documented_coverage(recorded))
    document = _document(
        config,
        episodes,
        split,
        censored_ids,
        excluded,
        leakage,
        metrics,
        constant,
        tree,
        risks,
    )
    _write_report(document, output_directory)
    return leakage, metrics, document


def _resolve_auto_features(
    config: RunConfig,
    signal_rows: Sequence[Mapping[str, str]],
) -> RunConfig:
    """Replace ``feature_columns: auto`` with the signal columns that are not ids.

    Args:
        config: Validated configuration.
        signal_rows: Loaded signal rows. Key order of the first row is kept.

    Returns:
        The same configuration when the allowlist is already explicit.
        Otherwise a copy whose feature list omits the identifier, the time
        columns, and ``exclude_columns``.

    Raises:
        ConfigurationError: Auto resolution would leave no feature column.
    """
    if isinstance(config.signals.feature_columns, list):
        return config
    if not signal_rows:
        raise ConfigurationError(
            "The signal table has no rows, so auto features cannot be resolved."
        )
    banned = {
        config.signals.id_column,
        config.signals.event_time_column,
        *config.signals.exclude_columns,
    }
    if config.signals.available_at_column is not None:
        banned.add(config.signals.available_at_column)
    features = [name for name in signal_rows[0] if name not in banned]
    if not features:
        raise ConfigurationError("feature_columns: auto resolved to an empty allowlist.")
    signals = config.signals.model_copy(update={"feature_columns": features})
    return config.model_copy(update={"signals": signals})


def _assign_split(
    config: RunConfig, group_identifiers: Sequence[str]
) -> dict[SplitName, tuple[str, ...]]:
    """Build the train, validation, and test membership.

    Args:
        config: Validated configuration.
        group_identifiers: Completed asset ids.

    Returns:
        Asset ids by split.

    Raises:
        ConfigurationError: The selected protocol block is missing or the
            official id files do not match the completed assets.
    """
    if config.split.protocol is SplitProtocol.GROUP_HOLDOUT:
        holdout = config.split.group_holdout
        if holdout is None:
            raise ConfigurationError("group_holdout requires its settings block.")
        return assign_splits(
            config.split.protocol,
            group_identifiers=group_identifiers,
            train_ratio=holdout.train_ratio,
            validation_ratio=holdout.validation_ratio,
            test_ratio=holdout.test_ratio,
            seed=config.project.seed,
        )
    partitions = config.split.official_partitions
    if partitions is None:
        raise ConfigurationError("official_partitions requires its id files.")
    return assign_official_partitions(
        group_identifiers,
        train_ids=read_split_ids(Path(partitions.train_ids)),
        validation_ids=read_split_ids(Path(partitions.validation_ids)),
        test_ids=read_split_ids(Path(partitions.test_ids)),
    )


def _separate_training_histories(
    episodes: Sequence[Episode],
    config: RunConfig,
) -> tuple[tuple[Episode, ...], tuple[tuple[Episode, HistoryDisposition], ...]]:
    """Keep censored and unsupported histories out of every split.

    Args:
        episodes: Classified asset histories.
        config: Label policy.

    Returns:
        Histories that may be split and fit, then histories that are only
        rejected or reported.
    """
    supervised: list[Episode] = []
    excluded: list[tuple[Episode, HistoryDisposition]] = []
    for episode in episodes:
        disposition = disposition_for_history(episode.support, config.labeling.censored_policy)
        if disposition in {HistoryDisposition.REJECT, HistoryDisposition.REPORT}:
            excluded.append((episode, disposition))
        else:
            supervised.append(episode)
    return tuple(supervised), tuple(excluded)


def _stop_when_censored_histories_are_rejected(
    config: RunConfig,
    episodes: Sequence[Episode],
    censored_ids: tuple[str, ...],
    excluded: Sequence[tuple[Episode, HistoryDisposition]],
    output_directory: Path,
) -> None:
    """Write a failed partial report, then stop, when policy is ``reject``.

    Args:
        config: Validated configuration.
        episodes: Classified histories.
        censored_ids: Censored or unsupported asset ids.
        excluded: Histories left out of every split, with their disposition.
        output_directory: Directory for the partial ``report.json``.

    Raises:
        ContractError: At least one history was rejected. The report is
            already on disk, with status ``FAILED``, the violations listed,
            and no metrics.
    """
    rejected = [
        (episode, disposition)
        for episode, disposition in excluded
        if disposition is HistoryDisposition.REJECT
    ]
    if not rejected:
        return
    violations = [
        {
            "asset_id": episode.asset_id,
            "support": episode.support.value,
            "disposition": disposition.value,
            "code": "censored_or_unsupported_history",
            "message": (
                "censored_policy reject stopped the run. "
                "This history was not placed in a split and was not used for training."
            ),
        }
        for episode, disposition in rejected
    ]
    document: dict[str, object] = {
        "project": config.project.name,
        "status": "FAILED",
        "disclaimer": _DISCLAIMER,
        "asset_count": len(episodes),
        "censored_or_unsupported_asset_ids": list(censored_ids),
        "dropped_asset_ids": [],
        "contract_violations": violations,
        "history_dispositions": [
            {
                "asset_id": episode.asset_id,
                "support": episode.support.value,
                "disposition": disposition.value,
                "used_for_training": False,
                "detail": (
                    "Rejected before any split was fit. "
                    "A censored or unsupported history is not a training row."
                ),
            }
            for episode, disposition in rejected
        ],
        "splits": None,
        "metrics": None,
        "risks": [],
        "headline_model": None,
        "tree_model_status": None,
    }
    report_path = _write_report(document, output_directory)
    listed = ", ".join(str(item["asset_id"]) for item in violations)
    raise ContractError(
        "censored_policy reject stopped the run. "
        f"A partial report with status FAILED was written to {report_path}. "
        "Censored or unsupported histories were not placed in a split "
        f"and were not used for training: {listed}."
    )


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


def _fit_tree(
    training_rows: Sequence[tuple[Mapping[str, float | None], float]],
    validation_rows: Sequence[tuple[Mapping[str, float | None], float]],
    *,
    random_state: int,
) -> FittedBaseline:
    """Fit the tree on training rows and early-stop on validation when it has rows.

    Args:
        training_rows: Training features and targets.
        validation_rows: Validation features and targets. Empty skips early stopping.
        random_state: Project seed.

    Returns:
        The fitted tree. Test rows are not accepted here.
    """
    validation_features = tuple(features for features, _ in validation_rows)
    validation_targets = tuple(target for _, target in validation_rows)
    return fit_histogram_gradient_boosting(
        training_features=tuple(features for features, _ in training_rows),
        training_targets=tuple(target for _, target in training_rows),
        validation_features=validation_features or None,
        validation_targets=validation_targets or None,
        random_state=random_state,
    )


def _early_stopping_risk(validation_asset_count: int, minimum: int) -> dict[str, object]:
    """Describe a tree fit that could not early-stop on validation.

    Args:
        validation_asset_count: Assets in the validation split.
        minimum: Configured minimum assets per split.

    Returns:
        A warning risk. The iteration count is the fixed cap, not a test choice.
    """
    return {
        "severity": "warning",
        "code": "early_stopping_not_applied",
        "split": SplitName.VALIDATION.value,
        "asset_count": validation_asset_count,
        "minimum_asset_count": minimum,
        "message": (
            "Validation has no scored rows, so histogram gradient boosting used "
            f"a fixed {FIXED_ITERATION_CAP} iterations on the training split only. "
            "Early stopping was not applied, and the test split was not used "
            "to choose the iteration count."
        ),
    }


def _completed_rows(
    labeled: Sequence[Mapping[str, object]],
    asset_ids: Sequence[str],
) -> list[tuple[dict[str, float | None], float]]:
    """Keep scored rows whose asset is in one split.

    Args:
        labeled: Prediction rows.
        asset_ids: Assets in the split.

    Returns:
        Feature mapping and remaining life for each scored row.
    """
    allowed = set(asset_ids)
    chosen: list[tuple[dict[str, float | None], float]] = []
    for row in labeled:
        if row["asset_id"] not in allowed or row["remaining_life"] is None:
            continue
        chosen.append((_feature_mapping(row["features"]), _number(row["remaining_life"])))
    return chosen


def _feature_mapping(value: object) -> dict[str, float | None]:
    """Read a causal feature mapping from a labeled row.

    Args:
        value: The ``features`` cell.

    Returns:
        Feature name to a float or None.

    Raises:
        ConfigurationError: The cell is not a feature mapping.
    """
    if not isinstance(value, Mapping):
        raise ConfigurationError("A labeled row is missing its feature mapping.")
    features: dict[str, float | None] = {}
    for key, cell in value.items():
        if not isinstance(key, str):
            raise ConfigurationError("Feature names must be strings.")
        if cell is None:
            features[key] = None
            continue
        features[key] = _number(cell)
    return features


def _metrics_report(
    rows_by_split: Mapping[SplitName, Sequence[tuple[Mapping[str, float | None], float]]],
    *,
    constant: FittedBaseline,
    tree: FittedBaseline | None,
    tree_requested: bool,
) -> MetricsReport:
    """Score validation and the final test after the models are frozen.

    Args:
        rows_by_split: Scored rows by split. Training rows are not scored here.
        constant: Model fit on the training split only.
        tree: Tree fit on the training split, or None when it was not requested.
        tree_requested: Whether the configuration asked for the tree.

    Returns:
        Validation and final-test metrics. An empty split is ``NOT_COMPUTED``.
    """
    return MetricsReport(
        validation=_split_metrics(
            rows_by_split[SplitName.VALIDATION],
            constant=constant,
            tree=tree,
            tree_requested=tree_requested,
        ),
        test=_split_metrics(
            rows_by_split[SplitName.TEST],
            constant=constant,
            tree=tree,
            tree_requested=tree_requested,
        ),
    )


def _split_metrics(
    rows: Sequence[tuple[Mapping[str, float | None], float]],
    *,
    constant: FittedBaseline,
    tree: FittedBaseline | None,
    tree_requested: bool,
) -> SplitMetrics:
    """Score one split.

    Args:
        rows: Scored rows in this split.
        constant: Training-only constant model.
        tree: Training-only tree, or None.
        tree_requested: Whether a missing tree is ``DISABLED`` rather than uncomputed.

    Returns:
        Root-mean-square error, mean absolute error, and the NASA score for
        each requested model. Empty splits are ``NOT_COMPUTED``.
    """
    values: dict[str, MetricValue] = {}
    if not rows:
        values.update(_absent_metrics("constant", MetricComputationStatus.NOT_COMPUTED))
        tree_status = (
            MetricComputationStatus.NOT_COMPUTED
            if tree_requested
            else MetricComputationStatus.DISABLED
        )
        values.update(_absent_metrics("hist_gradient_boosting", tree_status))
        return SplitMetrics(values=values)
    actual = tuple(target for _, target in rows)
    features = tuple(feature for feature, _ in rows)
    values.update(_scored_metrics("constant", actual, constant.predict(features)))
    if tree is None:
        values.update(_absent_metrics("hist_gradient_boosting", MetricComputationStatus.DISABLED))
    else:
        values.update(_scored_metrics("hist_gradient_boosting", actual, tree.predict(features)))
    return SplitMetrics(values=values)


def _absent_metrics(prefix: str, status: MetricComputationStatus) -> dict[str, MetricValue]:
    """Build null metrics for one model.

    Args:
        prefix: ``constant`` or ``hist_gradient_boosting``.
        status: ``NOT_COMPUTED`` or ``DISABLED``.

    Returns:
        The three metric names for that model.
    """
    metric = (
        MetricValue.not_computed()
        if status is MetricComputationStatus.NOT_COMPUTED
        else MetricValue.disabled()
    )
    return {f"{prefix}_{suffix}": metric for suffix in METRIC_SUFFIXES}


def _scored_metrics(
    prefix: str,
    actual: Sequence[float],
    predicted: Sequence[float],
) -> dict[str, MetricValue]:
    """Prefix the three computed scores for one model.

    Args:
        prefix: ``constant`` or ``hist_gradient_boosting``.
        actual: Observed remaining life.
        predicted: Predictions in the same order.

    Returns:
        Computed root-mean-square error, mean absolute error, and NASA score.
    """
    named = score_named_errors(actual=actual, predicted=predicted)
    return {f"{prefix}_{suffix}": named[suffix] for suffix in METRIC_SUFFIXES}


def _unsupported_history_finding(censored_ids: tuple[str, ...]) -> LeakageFinding:
    """Report censored assets instead of dropping them.

    Args:
        censored_ids: Assets that were not scored.

    Returns:
        A pass when every such asset is named, which this function always does.
    """
    if censored_ids:
        listed = ", ".join(censored_ids)
        evidence = (
            "Censored or unsupported assets were excluded from training "
            f"and listed in the report: {listed}."
        )
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


def _backend_split_finding(tree: FittedBaseline | None) -> LeakageFinding | None:
    """Record that the tree did not take a random internal validation split.

    Args:
        tree: Fitted tree, or None when the configuration did not ask for one.

    Returns:
        A pass when a tree was fit. None leaves the check ``NOT_CHECKED``.
    """
    if tree is None:
        return None
    if tree.early_stopping_split == "validation":
        evidence = (
            "Histogram gradient boosting was fit on the training split only. "
            "Early stopping used the validation split. validation_fraction was not set, "
            "so training rows were not held out at random."
        )
    else:
        evidence = (
            "Histogram gradient boosting was fit on the training split only with a fixed "
            "iteration count. Validation had no scored rows, so early stopping was not "
            "applied, and the test split was not used to choose iterations. "
            "validation_fraction was not set."
        )
    return LeakageFinding(
        check_id=LeakageCheckId.BACKEND_INTERNAL_SPLIT,
        status=LeakageStatus.PASS,
        evidence=evidence,
        remedy=(
            "Keep early stopping on the validation split. "
            "Do not sample a random internal split of the training rows."
        ),
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


_DISCLAIMER = (
    "Research software, not a safety-certified prognostic. "
    "A listed pass is not a guarantee that every leak was checked."
)
_HEADLINE_CRITERION = (
    "validation root_mean_square_error. The NASA score is reported and is not a gate."
)


def _write_report(document: dict[str, object], output_directory: Path) -> Path:
    """Write ``report.json`` and record its path on the document.

    Args:
        document: JSON-ready report body.
        output_directory: Directory for the file.

    Returns:
        The report path.
    """
    output_directory.mkdir(parents=True, exist_ok=True)
    report_path = output_directory / "report.json"
    document["report_json"] = str(report_path)
    report_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return report_path


def _document(
    config: RunConfig,
    episodes: Sequence[Episode],
    split: Mapping[SplitName, tuple[str, ...]],
    censored_ids: tuple[str, ...],
    excluded: Sequence[tuple[Episode, HistoryDisposition]],
    leakage: LeakageSuiteResult,
    metrics: MetricsReport,
    constant: FittedBaseline,
    tree: FittedBaseline | None,
    risks: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build the JSON report body for a run that finished scoring.

    Args:
        config: Validated configuration.
        episodes: Classified histories.
        split: Asset ids by split. Censored and unsupported ids are absent.
        censored_ids: Assets that were not scored.
        excluded: Histories left out of every split, with their disposition.
        leakage: Audit rows, including documented coverage.
        metrics: Validation and test metrics.
        constant: Training-only constant model.
        tree: Training-only tree, or None when it was not requested.
        risks: Warnings for empty or undersized splits.

    Returns:
        A JSON-ready mapping with status ``COMPLETED``.
    """
    headline = choose_headline(
        constant_validation_rmse=metrics.validation.values["constant_root_mean_square_error"],
        tree_validation_rmse=metrics.validation.values[
            "hist_gradient_boosting_root_mean_square_error"
        ],
    )
    tree_status = (
        MetricComputationStatus.COMPUTED if tree is not None else MetricComputationStatus.DISABLED
    )
    return {
        "project": config.project.name,
        "status": "COMPLETED",
        "disclaimer": _DISCLAIMER,
        "asset_count": len(episodes),
        "censored_or_unsupported_asset_ids": list(censored_ids),
        "dropped_asset_ids": [],
        "contract_violations": [],
        "history_dispositions": [
            {
                "asset_id": episode.asset_id,
                "support": episode.support.value,
                "disposition": disposition.value,
                "used_for_training": False,
                "detail": (
                    "Reported and excluded from every split. "
                    "A censored or unsupported history is not a training row."
                ),
            }
            for episode, disposition in excluded
        ],
        "splits": {name.value: list(identifiers) for name, identifiers in split.items()},
        "min_assets_per_split": config.split.min_assets_per_split,
        "risks": [dict(risk) for risk in risks],
        "constant_training_value": constant.constant_value,
        "constant_training_row_count": constant.training_row_count,
        "hist_gradient_boosting_training_row_count": (
            None if tree is None else tree.training_row_count
        ),
        "hist_gradient_boosting_iteration_count": None if tree is None else tree.iteration_count,
        "hist_gradient_boosting_max_iterations": None if tree is None else FIXED_ITERATION_CAP,
        "hist_gradient_boosting_random_state": None if tree is None else tree.random_state,
        "hist_gradient_boosting_early_stopping_split": (
            None if tree is None else tree.early_stopping_split
        ),
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
        "headline_model": headline.value,
        "headline_criterion": _HEADLINE_CRITERION,
        "tree_model_status": tree_status.value,
    }
