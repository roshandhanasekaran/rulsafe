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
from rulsafe.eval.bootstrap import (
    BOOTSTRAP_LEVEL,
    BOOTSTRAP_METHOD,
    BOOTSTRAP_SAMPLES,
    bootstrap_engine_intervals,
)
from rulsafe.eval.fd001 import (
    FD001_PROTOCOL_NAME,
    HELD_OUT_ROWS_PROTOCOL_NAME,
    NASA_SCORE_DEFINITION,
    cap_remaining_life,
    protocol_description,
    read_official_rul,
)
from rulsafe.eval.metrics import (
    METRIC_SUFFIXES,
    MetricsReport,
    SplitMetrics,
    choose_headline,
    score_with_per_engine_nasa,
)
from rulsafe.exceptions import ConfigurationError, ContractError
from rulsafe.io.files import load_table
from rulsafe.leakage.checks import LeakageFinding
from rulsafe.leakage.fail_on import (
    ObservedWindow,
    choice_split_finding,
    confirmed_fail_on_ids,
    delayed_record_finding,
    entity_leakage_finding,
    event_metadata_in_features_finding,
    future_in_features_finding,
    future_labels_finding,
    high_association_finding,
    interpolation_leak_finding,
    official_hidden_label_finding,
    post_event_features_finding,
    random_split_finding,
    replacement_episode_mix_finding,
    scaler_leakage_finding,
    silent_negative_censoring_finding,
    target_in_features_finding,
    unsupported_history_finding,
)
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
from rulsafe.pipeline.labels import (
    HistoryDisposition,
    HistorySupport,
    disposition_for_history,
)
from rulsafe.pipeline.prepare import (
    ScoredRow,
    prepare_official_last_observations,
    prepare_supervised,
)
from rulsafe.pipeline.preprocess import FittedPreprocessor, fit_preprocessors
from rulsafe.pipeline.split import (
    SplitName,
    assign_official_partitions,
    assign_splits,
    read_split_ids,
    split_size_risks,
)
from rulsafe.report.html import write_html_report
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
    prepared = prepare_supervised(supervised, config)
    split = _assign_split(config, tuple(episode.asset_id for episode in supervised))
    minimum = config.split.min_assets_per_split
    risks: list[dict[str, object]] = list(split_size_risks(split, minimum=minimum))
    rows_by_split = {
        name: _rows_for_assets(prepared.rows, identifiers) for name, identifiers in split.items()
    }
    training_rows = rows_by_split[SplitName.TRAIN]
    if not training_rows:
        raise ContractError("The training split has no completed-trajectory target.")
    unscaled_training = training_rows
    official_benchmark = config.evaluation.official_benchmark
    official_truths: dict[str, float] = {}
    official_rows: tuple[ScoredRow, ...] = ()
    official_windows: tuple[ObservedWindow, ...] = ()
    if official_benchmark is not None:
        official_truths = read_official_rul(Path(official_benchmark.rul_path))
        _require_censored_engines_in_rul(censored_ids, official_truths)
        official_rows, official_windows = prepare_official_last_observations(
            episodes, official_truths, config
        )
    preprocessor = fit_preprocessors(
        tuple(row.features for row in training_rows),
        asset_ids=tuple(row.asset_id for row in training_rows),
        feature_names=prepared.feature_names,
        clip_percentiles=config.preprocessing.clip_percentiles,
        scaler=config.preprocessing.scaler,
    )
    rows_by_split = {name: _transform(rows, preprocessor) for name, rows in rows_by_split.items()}
    training_rows = rows_by_split[SplitName.TRAIN]
    validation_rows = rows_by_split[SplitName.VALIDATION]
    official_rows = _transform(official_rows, preprocessor)
    constant = fit_constant_baseline(
        training_targets=tuple(row.remaining_life for row in training_rows)
    )
    tree_requested = BaselineName.HIST_GRADIENT_BOOSTING in config.models.include
    tree: FittedBaseline | None = None
    if tree_requested:
        tree = _fit_tree(training_rows, validation_rows, random_state=config.project.seed)
        if not validation_rows:
            risks.append(_early_stopping_risk(len(split[SplitName.VALIDATION]), minimum))
    for risk in risks:
        warnings.warn(str(risk["message"]), UserWarning, stacklevel=2)
    per_row_metrics = _metrics_report(
        rows_by_split, constant=constant, tree=tree, tree_requested=tree_requested
    )
    official = official_benchmark is not None
    if official:
        headline_rows = official_rows
        headline_metrics = MetricsReport(
            validation=per_row_metrics.validation,
            test=_split_metrics(
                official_rows,
                constant=constant,
                tree=tree,
                tree_requested=tree_requested,
            ),
        )
        official_validation_rows = _last_rows(validation_rows)
        official_validation = _split_metrics(
            official_validation_rows,
            constant=constant,
            tree=tree,
            tree_requested=tree_requested,
        )
    else:
        headline_rows = rows_by_split[SplitName.TEST]
        headline_metrics = per_row_metrics
        official_validation_rows = ()
        official_validation = None
    intervals = _confidence_intervals(
        headline_rows=headline_rows,
        secondary_rows=rows_by_split[SplitName.TEST] if official else None,
        constant=constant,
        tree=tree,
        seed=config.project.seed,
    )
    choice_ids = tuple(dict.fromkeys(row.asset_id for row in validation_rows))
    association_rows = tuple((row.features, row.remaining_life) for row in unscaled_training)
    recorded = _audit_findings(
        config=config,
        episodes=episodes,
        tables=tables,
        split=split,
        censored_ids=censored_ids,
        prepared_windows=prepared.windows,
        official_windows=official_windows,
        label_checks=_observed_label_triples(prepared.rows, tables, config),
        feature_names=prepared.feature_names,
        fit_asset_ids=preprocessor.fitted_asset_ids,
        labeled_asset_ids=tuple(row.asset_id for row in prepared.rows),
        official_asset_ids=tuple(official_truths),
        training_used_official_file=_training_targets_match_official_file(
            unscaled_training, official_truths, config.target.rul_cap
        ),
        early_stopping_asset_ids=choice_ids,
        selection_asset_ids=choice_ids,
        association_rows=association_rows,
        tree=tree,
    )
    leakage = LeakageSuiteResult(findings=with_documented_coverage(recorded))
    document = _document(
        config,
        episodes,
        split,
        censored_ids,
        excluded,
        leakage,
        headline_metrics,
        constant,
        tree,
        risks,
        official_asset_ids=set(official_truths),
        per_row_metrics=per_row_metrics,
        official_validation=official_validation,
        official_validation_count=len(official_validation_rows),
        official_test_count=len(official_rows),
        intervals=intervals,
        preprocessor=preprocessor,
        feature_names=prepared.feature_names,
    )
    confirmed = confirmed_fail_on_ids(leakage.findings, config.leakage.fail_on)
    if confirmed:
        document["status"] = "FAILED"
        document["confirmed_fail_on"] = list(confirmed)
    _write_report(document, output_directory)
    if confirmed:
        listed = ", ".join(confirmed)
        raise ContractError(
            f"A fail_on leakage check was CONFIRMED: {listed}. "
            f"The report was written to {output_directory / 'report.json'}."
        )
    return leakage, headline_metrics, document


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
        ConfigurationError: The selected protocol block is missing, the
            grouping column is unsupported, or the official id files do
            not match the completed assets.
    """
    protocol_name = _stored_name(config.split.protocol)
    if protocol_name == SplitProtocol.OFFICIAL_PARTITIONS.value:
        partitions = config.split.official_partitions
        if partitions is None:
            raise ConfigurationError("official_partitions requires its id files.")
        return assign_official_partitions(
            group_identifiers,
            train_ids=read_split_ids(Path(partitions.train_ids)),
            validation_ids=read_split_ids(Path(partitions.validation_ids)),
            test_ids=read_split_ids(Path(partitions.test_ids)),
        )
    holdout = config.split.group_holdout
    if holdout is None:
        raise ConfigurationError("group_holdout requires its settings block.")
    try:
        holdout.require_asset_id_column(config.assets.id_column)
    except ValueError as error:
        raise ConfigurationError(str(error)) from error
    if protocol_name not in {SplitProtocol.GROUP_HOLDOUT.value, "random"}:
        raise ConfigurationError(f"Unknown split protocol {protocol_name}.")
    return assign_splits(
        SplitProtocol.GROUP_HOLDOUT,
        group_identifiers=group_identifiers,
        train_ratio=holdout.train_ratio,
        validation_ratio=holdout.validation_ratio,
        test_ratio=holdout.test_ratio,
        seed=config.project.seed,
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
    violations = [_rejection_record(episode, disposition) for episode, disposition in rejected]
    document: dict[str, object] = {
        "project": config.project.name,
        "status": "FAILED",
        "disclaimer": _DISCLAIMER,
        "asset_count": len(episodes),
        "censored_or_unsupported_asset_ids": list(censored_ids),
        "dropped_asset_ids": [],
        "offending_asset_ids": [item["asset_id"] for item in violations],
        "offending_row_counts": [
            {
                "asset_id": item["asset_id"],
                "signal_row_count": item["signal_row_count"],
                "event_row_count": item["event_row_count"],
                "prediction_row_count": item["prediction_row_count"],
            }
            for item in violations
        ],
        "contract_violations": violations,
        "history_dispositions": [
            {
                "asset_id": episode.asset_id,
                "support": episode.support.value,
                "disposition": disposition.value,
                "used_for_training": False,
                "signal_row_count": len(episode.rows),
                "event_row_count": episode.event_row_count,
                "prediction_row_count": len(_prediction_times(episode)),
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
    listed = "; ".join(
        (
            f"{item['asset_id']} (signal_row_count={item['signal_row_count']}, "
            f"event_row_count={item['event_row_count']}, "
            f"prediction_row_count={item['prediction_row_count']})"
        )
        for item in violations
    )
    raise ContractError(
        "censored_policy reject stopped the run. "
        f"A partial report with status FAILED was written to {report_path}. "
        "Offending assets and row counts: "
        f"{listed}."
    )


def _rejection_record(episode: Episode, disposition: HistoryDisposition) -> dict[str, object]:
    """Describe one censored or unsupported asset that stopped the run.

    Args:
        episode: History that was not placed in a split.
        disposition: ``reject``.

    Returns:
        The asset id and the signal, event, and prediction row counts.
    """
    signal_row_count = len(episode.rows)
    event_row_count = episode.event_row_count
    prediction_row_count = len(_prediction_times(episode))
    return {
        "asset_id": episode.asset_id,
        "support": episode.support.value,
        "disposition": disposition.value,
        "code": "censored_or_unsupported_history",
        "signal_row_count": signal_row_count,
        "event_row_count": event_row_count,
        "prediction_row_count": prediction_row_count,
        "message": (
            "censored_policy reject stopped the run. "
            f"Asset {episode.asset_id} was not placed in a split and was not used for training. "
            f"signal_row_count={signal_row_count}, event_row_count={event_row_count}, "
            f"prediction_row_count={prediction_row_count}."
        ),
    }


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
    training_rows: Sequence[ScoredRow],
    validation_rows: Sequence[ScoredRow],
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
    validation_features = tuple(row.features for row in validation_rows)
    validation_targets = tuple(row.remaining_life for row in validation_rows)
    return fit_histogram_gradient_boosting(
        training_features=tuple(row.features for row in training_rows),
        training_targets=tuple(row.remaining_life for row in training_rows),
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


def _rows_for_assets(rows: Sequence[ScoredRow], asset_ids: Sequence[str]) -> tuple[ScoredRow, ...]:
    """Keep scored rows whose asset is in one split.

    Args:
        rows: Prediction rows.
        asset_ids: Assets in the split.

    Returns:
        The rows that belong to those assets.
    """
    allowed = set(asset_ids)
    return tuple(row for row in rows if row.asset_id in allowed)


def _transform(
    rows: Sequence[ScoredRow], preprocessor: FittedPreprocessor
) -> tuple[ScoredRow, ...]:
    """Apply the training-fitted clip and scaler.

    Args:
        rows: Rows whose features are still on the original scale.
        preprocessor: Clip and scaler fit on the training split.

    Returns:
        Rows with transformed features and the same targets.
    """
    return tuple(
        ScoredRow(
            asset_id=row.asset_id,
            prediction_time=row.prediction_time,
            features=preprocessor.transform(row.features),
            remaining_life=row.remaining_life,
        )
        for row in rows
    )


def _last_rows(rows: Sequence[ScoredRow]) -> tuple[ScoredRow, ...]:
    """Keep the latest prediction time of each asset.

    Args:
        rows: Scored rows.

    Returns:
        One row per asset, in asset-id order.
    """
    best: dict[str, ScoredRow] = {}
    for row in rows:
        current = best.get(row.asset_id)
        if current is None or row.prediction_time >= current.prediction_time:
            best[row.asset_id] = row
    return tuple(best[asset_id] for asset_id in sorted(best))


def _require_censored_engines_in_rul(
    censored_ids: tuple[str, ...],
    truths: Mapping[str, float],
) -> None:
    """Require every censored engine to have an official truth.

    Args:
        censored_ids: Censored asset ids.
        truths: Official remaining life by asset id.

    Raises:
        ConfigurationError: A censored engine is missing from the RUL file.
    """
    missing = [asset_id for asset_id in censored_ids if asset_id not in truths]
    if missing:
        listed = ", ".join(missing)
        raise ConfigurationError(
            f"Censored engines are missing from the official RUL file: {listed}."
        )


def _metrics_report(
    rows_by_split: Mapping[SplitName, Sequence[ScoredRow]],
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
    rows: Sequence[ScoredRow],
    *,
    constant: FittedBaseline,
    tree: FittedBaseline | None,
    tree_requested: bool,
) -> SplitMetrics:
    """Score one split.

    Root-mean-square error and mean absolute error use every row. The NASA
    score uses the last scored time of each engine.

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
    features = tuple(row.features for row in rows)
    values.update(_scored_metrics("constant", rows, constant.predict(features)))
    if tree is None:
        values.update(_absent_metrics("hist_gradient_boosting", MetricComputationStatus.DISABLED))
    else:
        values.update(_scored_metrics("hist_gradient_boosting", rows, tree.predict(features)))
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
    rows: Sequence[ScoredRow],
    predicted: Sequence[float],
) -> dict[str, MetricValue]:
    """Prefix the three computed scores for one model.

    Args:
        prefix: ``constant`` or ``hist_gradient_boosting``.
        rows: Scored rows. The NASA score keeps one pair per engine.
        predicted: Predictions in the same order.

    Returns:
        Computed root-mean-square error, mean absolute error, and NASA score.
    """
    named = score_with_per_engine_nasa(
        asset_ids=tuple(row.asset_id for row in rows),
        times=tuple(row.prediction_time for row in rows),
        actual=tuple(row.remaining_life for row in rows),
        predicted=predicted,
    )
    return {f"{prefix}_{suffix}": named[suffix] for suffix in METRIC_SUFFIXES}


def _confidence_intervals(
    *,
    headline_rows: Sequence[ScoredRow],
    secondary_rows: Sequence[ScoredRow] | None,
    constant: FittedBaseline,
    tree: FittedBaseline | None,
    seed: int,
) -> dict[str, object]:
    """Bootstrap test RMSE and MAE over engines.

    Args:
        headline_rows: Rows behind the headline test.
        secondary_rows: Per-row secondary test, or None when it is the headline.
        constant: Training-only constant model.
        tree: Training-only tree, or None.
        seed: Project seed.

    Returns:
        Method, sample count, level, seed, and the two test blocks.
    """
    return {
        "method": BOOTSTRAP_METHOD,
        "samples": BOOTSTRAP_SAMPLES,
        "level": BOOTSTRAP_LEVEL,
        "seed": seed,
        "headline_test": _model_intervals(headline_rows, constant, tree, seed),
        "secondary_test": (
            None
            if secondary_rows is None
            else _model_intervals(secondary_rows, constant, tree, seed)
        ),
    }


def _model_intervals(
    rows: Sequence[ScoredRow],
    constant: FittedBaseline,
    tree: FittedBaseline | None,
    seed: int,
) -> dict[str, object]:
    """Bootstrap one test view for each fitted model.

    Args:
        rows: Scored rows. Empty views are ``NOT_COMPUTED``.
        constant: Training-only constant model.
        tree: Training-only tree, or None.
        seed: Project seed.

    Returns:
        Status and one interval block per model.
    """
    if not rows:
        return {"status": MetricComputationStatus.NOT_COMPUTED.value, "models": {}}
    features = tuple(row.features for row in rows)
    actual = tuple(row.remaining_life for row in rows)
    assets = tuple(row.asset_id for row in rows)
    models: dict[str, object] = {
        "constant": bootstrap_engine_intervals(
            asset_ids=assets,
            actual=actual,
            predicted=constant.predict(features),
            seed=seed,
        )
    }
    if tree is not None:
        models["hist_gradient_boosting"] = bootstrap_engine_intervals(
            asset_ids=assets,
            actual=actual,
            predicted=tree.predict(features),
            seed=seed,
        )
    return {"status": MetricComputationStatus.COMPUTED.value, "models": models}


def _audit_findings(
    *,
    config: RunConfig,
    episodes: Sequence[Episode],
    tables: LogicalTables,
    split: Mapping[SplitName, tuple[str, ...]],
    censored_ids: tuple[str, ...],
    prepared_windows: Sequence[ObservedWindow],
    official_windows: Sequence[ObservedWindow],
    label_checks: Sequence[tuple[float, float, float]],
    feature_names: Sequence[str],
    fit_asset_ids: Sequence[str],
    labeled_asset_ids: Sequence[str],
    official_asset_ids: Sequence[str],
    training_used_official_file: bool,
    early_stopping_asset_ids: Sequence[str],
    selection_asset_ids: Sequence[str],
    association_rows: Sequence[tuple[Mapping[str, float | None], float]],
    tree: FittedBaseline | None,
) -> list[LeakageFinding]:
    """Run the fail-on checks, the association warning, and the backend warning.

    The arguments that used to be copied from the same list, or passed as a
    literal, are computed by the caller from the fitted preprocessor, the
    event table, and the rows that early stopping and selection actually saw.

    Args:
        config: Validated configuration.
        episodes: Classified histories.
        tables: Loaded tables, used for replacement events and history scans.
        split: Asset ids by split.
        censored_ids: Censored or unsupported assets named in the report.
        prepared_windows: Windows for supervised rows.
        official_windows: Windows for the official last observation.
        label_checks: ``(prediction time, failure time from the event table, label)``.
        feature_names: Names passed to the model.
        fit_asset_ids: Assets recorded on the fitted preprocessor.
        labeled_asset_ids: Assets that received a supervised label.
        official_asset_ids: Engines named in the official RUL file.
        training_used_official_file: True when a training label equals that file.
        early_stopping_asset_ids: Assets whose rows were passed to early stopping.
        selection_asset_ids: Assets whose validation scores chose the model.
        association_rows: Unscaled training features and targets.
        tree: Fitted tree, or None.

    Returns:
        Findings. A missing check stays for documented coverage.
    """
    windows = tuple(prepared_windows) + tuple(official_windows)
    split_ids = tuple(asset_id for identifiers in split.values() for asset_id in identifiers)
    competing_ids = _event_ids(tables, config, config.events.competing_types)
    findings = [
        random_split_finding(_stored_name(config.split.protocol)),
        future_labels_finding(label_checks, config.target.rul_cap),
        future_in_features_finding(windows),
        post_event_features_finding(windows),
        delayed_record_finding(
            available_at_supplied=config.signals.available_at_column is not None,
            windows=windows,
        ),
        interpolation_leak_finding(_stored_name(config.signals.gap_policy)),
        entity_leakage_finding(windows),
        scaler_leakage_finding(fit_asset_ids, split[SplitName.TRAIN]),
        target_in_features_finding(feature_names, association_rows),
        event_metadata_in_features_finding(feature_names, config.events.forbidden_as_features),
        silent_negative_censoring_finding(competing_ids, split_ids, labeled_asset_ids),
        unsupported_history_finding(_ids_requiring_a_report(tables, config), censored_ids),
        replacement_episode_mix_finding(
            _episode_spans(episodes), _replacement_events(tables, config)
        ),
        choice_split_finding(
            early_stopping_asset_ids,
            selection_asset_ids,
            split[SplitName.TEST],
        ),
        official_hidden_label_finding(
            train_asset_ids=split[SplitName.TRAIN],
            official_asset_ids=official_asset_ids,
            training_used_official_file=training_used_official_file,
        ),
        high_association_finding(
            association_rows,
            threshold=config.leakage.association_warn_threshold,
        ),
    ]
    backend = _backend_split_finding(tree)
    if backend is not None:
        findings.append(backend)
    return findings


def _stored_name(value: object) -> str:
    """Return the value of an enum, or the string that was stored in its place.

    A validated configuration stores an enum. A planted leak can store the
    raw protocol or gap name without passing schema validation.

    Args:
        value: Enum or string.

    Returns:
        The protocol or policy name.
    """
    raw = getattr(value, "value", value)
    return str(raw)


def _table_ids(rows: Sequence[Mapping[str, str]], column_name: str) -> set[str]:
    """Return the non-blank identifiers in one column.

    Args:
        rows: Loaded table rows.
        column_name: Identifier header.

    Returns:
        Stripped identifiers.
    """
    return {row.get(column_name, "").strip() for row in rows if row.get(column_name, "").strip()}


def _event_ids(
    tables: LogicalTables, config: RunConfig, event_types: Sequence[str]
) -> tuple[str, ...]:
    """Return assets that have one of the named event types.

    Args:
        tables: Loaded tables.
        config: Event column names.
        event_types: Types to keep.

    Returns:
        Sorted asset ids.
    """
    wanted = {event_type.casefold() for event_type in event_types}
    found: set[str] = set()
    for row in tables.events.rows:
        if row.get(config.events.type_column, "").casefold() not in wanted:
            continue
        asset_id = row.get(config.events.id_column, "").strip()
        if asset_id:
            found.add(asset_id)
    return tuple(sorted(found))


def _ids_requiring_a_report(tables: LogicalTables, config: RunConfig) -> tuple[str, ...]:
    """Return assets the report must name as censored or unsupported.

    An asset with a terminal failure and no competing close is completed, so
    it is not in this list. Every other asset that appears in the asset table
    or the signal table must be named. The scan reads the tables. It does not
    read the episode list the report is about to write.

    Args:
        tables: Loaded tables.
        config: Identifier columns and event types.

    Returns:
        Sorted asset ids.
    """
    present = _table_ids(tables.assets.rows, config.assets.id_column) | _table_ids(
        tables.signals.rows, config.signals.id_column
    )
    terminal = set(_event_ids(tables, config, config.events.terminal_types))
    competing = set(_event_ids(tables, config, config.events.competing_types))
    required = [
        asset_id
        for asset_id in sorted(present)
        if asset_id in competing or asset_id not in terminal
    ]
    return tuple(required)


def _observed_label_triples(
    rows: Sequence[ScoredRow],
    tables: LogicalTables,
    config: RunConfig,
) -> tuple[tuple[float, float, float], ...]:
    """Pair each scored label with the failure time read from the event table.

    Args:
        rows: Supervised rows. Their labels are the values under test.
        tables: Loaded tables.
        config: Event columns and terminal types.

    Returns:
        ``(prediction time, failure time, label)``. A row with no failure
        event is paired with a time that cannot equal its label.
    """
    ends: dict[str, float] = {}
    wanted = {event_type.casefold() for event_type in config.events.terminal_types}
    for event_row in tables.events.rows:
        if event_row.get(config.events.type_column, "").casefold() not in wanted:
            continue
        asset_id = event_row.get(config.events.id_column, "").strip()
        raw_time = event_row.get(config.events.event_time_column, "")
        if not asset_id or raw_time == "":
            continue
        event_time = _number(raw_time)
        current = ends.get(asset_id)
        if current is None or event_time < current:
            ends[asset_id] = event_time
    triples: list[tuple[float, float, float]] = []
    for scored in rows:
        end = ends.get(scored.asset_id)
        if end is None:
            end = scored.prediction_time - scored.remaining_life - 1.0
        triples.append((scored.prediction_time, end, scored.remaining_life))
    return tuple(triples)


def _training_targets_match_official_file(
    rows: Sequence[ScoredRow],
    truths: Mapping[str, float],
    rul_cap: int | None,
) -> bool:
    """Return whether a training label equals the official file for that asset.

    Args:
        rows: Unscaled training rows.
        truths: Official remaining life by asset id.
        rul_cap: Piecewise cap, or None.

    Returns:
        True when a training target matches the capped file value of its asset.
    """
    for row in rows:
        truth = truths.get(row.asset_id)
        if truth is None:
            continue
        expected = cap_remaining_life(truth, rul_cap)
        scale = max(1.0, abs(expected))
        if abs(row.remaining_life - expected) <= 1e-6 * scale:
            return True
    return False


def _episode_spans(episodes: Sequence[Episode]) -> dict[str, tuple[float, float]]:
    """Return the first and last signal time of each episode.

    Args:
        episodes: Classified histories.

    Returns:
        Asset id to ``(start, end)``. An empty history is omitted.
    """
    spans: dict[str, tuple[float, float]] = {}
    for episode in episodes:
        if not episode.rows:
            continue
        times = [_number(row["event_time"]) for row in episode.rows]
        spans[episode.asset_id] = (min(times), max(times))
    return spans


def _replacement_events(
    tables: LogicalTables,
    config: RunConfig,
) -> tuple[tuple[str, float], ...]:
    """Read replacement events as asset id and time.

    Args:
        tables: Loaded tables.
        config: Event column names and replacement types.

    Returns:
        One pair per replacement row. Other event types are ignored.
    """
    types = {item.casefold() for item in config.contract.replacement_types}
    if not types:
        return ()
    found: list[tuple[str, float]] = []
    for row in tables.events.rows:
        if row.get(config.events.type_column, "").casefold() not in types:
            continue
        asset_id = row.get(config.events.id_column, "").strip()
        raw_time = row.get(config.events.event_time_column, "")
        if not asset_id or raw_time == "":
            continue
        found.append((asset_id, _number(raw_time)))
    return tuple(found)


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
VALIDATION_METRIC_ROLE = "used for early stopping/selection"
TEST_METRIC_ROLE = "headline evaluation"
SECONDARY_METRIC_ROLE = "secondary"
_SELECTION_VIEW = "per-row remaining life on held-out training engines"
_OFFICIAL_TEST_VIEW = "last observation of each official test engine against the RUL file"
_ROW_TEST_VIEW = "per-row remaining life on the held-out test engines"
_OFFICIAL_VALIDATION_ROLE = "official-protocol validation, not used for early stopping"


def _headline_criterion(official: bool, rul_cap: int | None) -> str:
    """Describe which test is the headline and how the NASA score is summed.

    Args:
        official: True when the FD001 last-observation benchmark is the headline.
        rul_cap: Piecewise cap, or None.

    Returns:
        The criterion stored on the report.
    """
    cap_text = "none" if rul_cap is None else str(rul_cap)
    nasa = (
        "The NASA score is the Saxena 2008 sum of one term per engine, "
        "not a sum over rows. The NASA score is reported and is not a gate."
    )
    if official:
        return (
            "The headline evaluation is the test split: the last observation of each "
            "official test engine against the RUL file. Validation metrics are "
            f"{VALIDATION_METRIC_ROLE}. Those validation metrics are per-row scores "
            "on held-out training engines and do not use the official test labels. "
            f"Piecewise RUL cap: {cap_text}. {nasa} "
            "The per-row scores on held-out completed training engines are secondary."
        )
    return (
        "The headline evaluation is the test split of the model selected on "
        "validation root_mean_square_error. Validation metrics are "
        f"{VALIDATION_METRIC_ROLE} and are optimistic relative to the test. "
        f"Piecewise RUL cap: {cap_text}. {nasa}"
    )


def _write_report(document: dict[str, object], output_directory: Path) -> Path:
    """Write ``report.json`` and ``report.html``.

    Args:
        document: JSON-ready report body.
        output_directory: Directory for the files.

    Returns:
        The JSON report path.
    """
    output_directory.mkdir(parents=True, exist_ok=True)
    report_path = output_directory / "report.json"
    html_path = output_directory / "report.html"
    document["report_json"] = str(report_path)
    document["report_html"] = str(html_path)
    report_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    write_html_report(document, html_path)
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
    *,
    official_asset_ids: set[str],
    per_row_metrics: MetricsReport,
    official_validation: SplitMetrics | None,
    official_validation_count: int,
    official_test_count: int,
    intervals: Mapping[str, object],
    preprocessor: FittedPreprocessor,
    feature_names: Sequence[str],
) -> dict[str, object]:
    """Build the JSON report body for a run that finished scoring.

    Args:
        config: Validated configuration.
        episodes: Classified histories.
        split: Asset ids by split. Censored and unsupported ids are absent.
        censored_ids: Assets that were not scored as supervised rows.
        excluded: Histories left out of every split, with their disposition.
        leakage: Audit rows, including documented coverage.
        metrics: Selection metrics and the headline test.
        constant: Training-only constant model.
        tree: Training-only tree, or None when it was not requested.
        risks: Warnings for empty or undersized splits.
        official_asset_ids: Engines scored against the official RUL file.
        per_row_metrics: Per-row scores on held-out training engines.
        official_validation: Last-cycle scores of held-out training engines.
        official_validation_count: Engines in that official validation view.
        official_test_count: Official test engines.
        intervals: Bootstrap intervals for the test scores.
        preprocessor: Train-only clip and scaler.
        feature_names: Last, mean, and slope names passed to the model.

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
    official = config.evaluation.official_benchmark is not None
    rul_cap = config.target.rul_cap
    test_view = _OFFICIAL_TEST_VIEW if official else _ROW_TEST_VIEW
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
                "detail": _history_detail(episode.asset_id, official_asset_ids),
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
        "gap_policy": _stored_name(config.signals.gap_policy),
        "rul_cap": rul_cap,
        "feature_names": list(feature_names),
        "preprocessing": {
            "clip_percentiles": list(config.preprocessing.clip_percentiles),
            "scaler": preprocessor.scaler,
            "fit_split": preprocessor.membership.split_name,
            "fit_row_count": preprocessor.membership.fitted_row_count,
            "membership_hash": preprocessor.membership.membership_hash,
        },
        "windows": {
            "lookback": config.windows.lookback,
            "stride": config.windows.stride,
            "discard_straddle_split": config.windows.discard_straddle_split,
            "statistics": ["last", "mean", "slope"],
            "past_only": "event_time and available_at at or before the prediction time",
        },
        "evaluation_protocol": {
            "name": FD001_PROTOCOL_NAME if official else HELD_OUT_ROWS_PROTOCOL_NAME,
            "rul_cap": rul_cap,
            "nasa_score": NASA_SCORE_DEFINITION,
            "description": protocol_description(official=official, rul_cap=rul_cap),
        },
        "official_benchmark": _official_benchmark_block(
            config,
            test_metrics=metrics.test,
            validation_metrics=official_validation,
            validation_count=official_validation_count,
            test_count=official_test_count,
        ),
        "secondary_evaluation": (_secondary_block(per_row_metrics) if official else None),
        "confidence_intervals": dict(intervals),
        "leakage": [
            {
                "check_id": finding.check_id.value,
                "status": finding.status.value,
                "evidence": finding.evidence,
                "remedy": finding.remedy,
            }
            for finding in leakage.findings
        ],
        "selection_split": "validation",
        "headline_split": "test",
        "metric_roles": {
            "validation": VALIDATION_METRIC_ROLE,
            "test": TEST_METRIC_ROLE,
        },
        "metrics": {
            "validation": _metric_block(
                metrics.validation, VALIDATION_METRIC_ROLE, _SELECTION_VIEW
            ),
            "test": _metric_block(metrics.test, TEST_METRIC_ROLE, test_view),
        },
        "headline_model": headline.value,
        "headline_criterion": _headline_criterion(official, rul_cap),
        "headline_metrics": _headline_metrics(headline, metrics.test),
        "tree_model_status": tree_status.value,
    }


def _history_detail(asset_id: str, official_asset_ids: set[str]) -> str:
    """Describe a history that was left out of the supervised splits.

    Args:
        asset_id: Equipment identifier.
        official_asset_ids: Engines scored against the official RUL file.

    Returns:
        The disposition detail.
    """
    detail = (
        "Reported and excluded from every split. "
        "A censored or unsupported history is not a training row."
    )
    if asset_id in official_asset_ids:
        detail += " It is scored only in the official last-observation benchmark."
    return detail


def _official_benchmark_block(
    config: RunConfig,
    *,
    test_metrics: SplitMetrics,
    validation_metrics: SplitMetrics | None,
    validation_count: int,
    test_count: int,
) -> dict[str, object] | None:
    """Describe the FD001 last-observation benchmark.

    Args:
        config: Validated configuration.
        test_metrics: Headline scores on the official test engines.
        validation_metrics: Last-cycle scores of held-out training engines.
        validation_count: Engines in that validation view.
        test_count: Official test engines.

    Returns:
        The benchmark block, or None when this run has no official file.
    """
    benchmark = config.evaluation.official_benchmark
    if benchmark is None or validation_metrics is None:
        return None
    return {
        "protocol": FD001_PROTOCOL_NAME,
        "role": TEST_METRIC_ROLE,
        "rul_cap": config.target.rul_cap,
        "rul_path": str(benchmark.rul_path),
        "truth": (
            "RUL file value at the last observed cycle of each official test engine. "
            "The file is not a training label. When rul_cap is set, the scored truth "
            "is min(file value, rul_cap)."
        ),
        "validation_source": (
            "Last pre-failure cycle of each held-out training engine. "
            "Truth is the capped cycles remaining until failure."
        ),
        "early_stopping": (
            "Every causal row of the held-out training engines. "
            "The official test labels are not used for early stopping or model selection."
        ),
        "validation": {
            "engine_count": validation_count,
            "source": "last pre-failure cycle of held-out training engines",
            "role": _OFFICIAL_VALIDATION_ROLE,
            "metrics": _metric_block(
                validation_metrics,
                _OFFICIAL_VALIDATION_ROLE,
                "last pre-failure cycle of each held-out training engine",
            ),
        },
        "test": {
            "engine_count": test_count,
            "source": "last observed cycle of each official test engine",
            "role": TEST_METRIC_ROLE,
            "metrics": _metric_block(test_metrics, TEST_METRIC_ROLE, _OFFICIAL_TEST_VIEW),
        },
    }


def _secondary_block(metrics: MetricsReport) -> dict[str, object]:
    """Describe the per-row scores on held-out completed training engines.

    Args:
        metrics: Per-row validation and test scores.

    Returns:
        The secondary view. It is not the official FD001 benchmark.
    """
    return {
        "role": SECONDARY_METRIC_ROLE,
        "name": "held_out_training_engine_rows",
        "description": (
            "Per-row remaining life on held-out completed training engines. "
            "Not the official FD001 benchmark. The validation block is the same "
            "per-row scores used for early stopping and selection. The test block "
            "is the secondary evaluation. Its NASA score is one Saxena term per engine."
        ),
        "metrics": {
            "validation": _metric_block(
                metrics.validation, VALIDATION_METRIC_ROLE, _SELECTION_VIEW
            ),
            "test": _metric_block(
                metrics.test,
                SECONDARY_METRIC_ROLE,
                "per-row remaining life on held-out completed training engines",
            ),
        },
    }


def _metric_block(metrics: SplitMetrics, role: str, view: str) -> dict[str, object]:
    """Label one split's scores with the role and the view they come from.

    Args:
        metrics: Scores for one view.
        role: How this block is used.
        view: Which rows were scored.

    Returns:
        The role, the view, and the metric objects.
    """
    block: dict[str, object] = {"role": role, "view": view}
    block.update({name: metric.to_dict() for name, metric in metrics.values.items()})
    return block


def _headline_metrics(headline: BaselineName, test_metrics: SplitMetrics) -> dict[str, object]:
    """Copy the selected model's test scores into the headline block.

    Args:
        headline: Model selected on validation root-mean-square error.
        test_metrics: Final-test scores. They were not used to choose the model.

    Returns:
        The test scores of the selected model.
    """
    prefix = headline.value
    return {
        "split": "test",
        "role": TEST_METRIC_ROLE,
        "model": prefix,
        "root_mean_square_error": test_metrics.values[f"{prefix}_root_mean_square_error"].to_dict(),
        "mean_absolute_error": test_metrics.values[f"{prefix}_mean_absolute_error"].to_dict(),
        "nasa_score": test_metrics.values[f"{prefix}_nasa_score"].to_dict(),
    }
