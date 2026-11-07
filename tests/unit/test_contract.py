"""Contract, history disposition, audit coverage, and dataset cards."""

from pathlib import Path

import pytest

from rulsafe.config import CensoredHistoryPolicy, LeakageCheckId, LeakageStatus
from rulsafe.contract import (
    LogicalTableRole,
    episode_rule,
    required_columns,
    table_suffix_is_supported,
)
from rulsafe.datasets.registry import dataset_card, fetch_dataset, list_datasets
from rulsafe.eval.alerts import fleet_alert_coverage
from rulsafe.exceptions import ConfigurationError
from rulsafe.io.files import load_table
from rulsafe.leakage.checks import LeakageFinding
from rulsafe.leakage.report import format_finding, with_documented_coverage
from rulsafe.leakage.suite import worst_leakage_status
from rulsafe.pipeline.labels import HistoryDisposition, HistorySupport, disposition_for_history
from rulsafe.pipeline.preprocess import TransformerMembership


def test_required_columns_and_episode_default() -> None:
    assert required_columns(LogicalTableRole.SIGNALS) == ("asset_id", "event_time")
    assert required_columns(LogicalTableRole.EVENTS)[-1] == "event_type"
    rule = episode_rule()
    assert rule.replacement_starts_new_episode is True
    assert table_suffix_is_supported(Path("signals.parquet"))
    assert not table_suffix_is_supported(Path("signals.xlsx"))


def test_unsupported_suffix_is_rejected_before_read() -> None:
    with pytest.raises(ConfigurationError, match="parquet"):
        load_table(Path("signals.xlsx"), LogicalTableRole.SIGNALS)
    with pytest.raises(ConfigurationError, match="Could not read"):
        load_table(Path("signals.parquet"), LogicalTableRole.SIGNALS)


def test_censored_histories_are_not_dropped() -> None:
    dispositions = {
        disposition_for_history(support, policy)
        for support in (HistorySupport.CENSORED, HistorySupport.UNSUPPORTED)
        for policy in CensoredHistoryPolicy
    }
    assert HistoryDisposition.TRAIN not in dispositions
    assert "drop" not in {item.value for item in HistoryDisposition}
    assert (
        disposition_for_history(HistorySupport.CENSORED, CensoredHistoryPolicy.REJECT)
        is HistoryDisposition.REJECT
    )
    assert (
        disposition_for_history(HistorySupport.UNSUPPORTED, CensoredHistoryPolicy.REPORT)
        is HistoryDisposition.REPORT
    )
    assert (
        disposition_for_history(HistorySupport.COMPLETED, CensoredHistoryPolicy.REJECT)
        is HistoryDisposition.TRAIN
    )
    assert (
        disposition_for_history(
            HistorySupport.OFFICIAL_LAST_OBSERVATION,
            CensoredHistoryPolicy.REJECT,
        )
        is HistoryDisposition.SCORE_LAST_OBSERVATION
    )


def test_audit_coverage_does_not_treat_a_missing_check_as_a_pass() -> None:
    recorded = LeakageFinding(
        check_id=LeakageCheckId.UNSUPPORTED_HISTORY,
        status=LeakageStatus.CONFIRMED,
        evidence="A censored engine was omitted from the export.",
        remedy="Reject or report the engine. Do not drop it.",
    )
    documented = with_documented_coverage((recorded,))
    by_id = {finding.check_id: finding for finding in documented}
    assert by_id[LeakageCheckId.UNSUPPORTED_HISTORY].status is LeakageStatus.CONFIRMED
    assert by_id[LeakageCheckId.FUTURE_IN_FEATURES].status is LeakageStatus.NOT_CHECKED
    assert set(by_id) == set(LeakageCheckId)
    assert worst_leakage_status(()) is LeakageStatus.NOT_CHECKED
    assert worst_leakage_status(documented) is LeakageStatus.CONFIRMED
    text = format_finding(recorded)
    assert "check_id: unsupported_history" in text
    assert "status: CONFIRMED" in text


def test_transformer_membership_is_train_only() -> None:
    record = TransformerMembership(
        transformer_name="standard_scaler",
        split_name="train",
        fitted_row_count=10,
        membership_hash="abc",
        statistics={"mean": 0.0},
    )
    assert record.split_name == "train"
    with pytest.raises(ValueError, match="train split only"):
        TransformerMembership(
            transformer_name="standard_scaler",
            split_name="test",
            fitted_row_count=10,
            membership_hash="abc",
            statistics={},
        )


def test_dataset_cards_keep_licence_statements_separate() -> None:
    names = [card.name for card in list_datasets()]
    assert names == ["cmapss_fd001", "scania_component_x"]
    cmapss = dataset_card("cmapss_fd001")
    scania = dataset_card("scania_component_x")
    assert cmapss.available_in == "0.1"
    assert cmapss.licence is None
    assert "not specified" in cmapss.licence_statement.lower()
    assert cmapss.separate_record_note is not None
    assert "Zenodo" in cmapss.separate_record_note
    assert "CC BY 4.0" in cmapss.separate_record_note
    assert scania.available_in == "0.2"
    assert scania.licence == "CC-BY-4.0"
    assert scania.signal_column_count == 105
    assert fleet_alert_coverage() == "not_covered"
    with pytest.raises(ConfigurationError, match=r"v0\.2"):
        fetch_dataset("scania_component_x")
    with pytest.raises(ConfigurationError, match="Unknown dataset"):
        dataset_card("not-a-dataset")


def test_finding_text_and_baseline_record_are_explicit() -> None:
    import rulsafe.eval.plots as plots
    import rulsafe.models.baselines as baselines
    from rulsafe.api import ReportPaths, RunResult
    from rulsafe.config import BaselineName
    from rulsafe.eval.metrics import MetricsReport, SplitMetrics
    from rulsafe.leakage.checks import AuditContext
    from rulsafe.leakage.suite import LeakageSuiteResult
    from rulsafe.models.baselines import FittedBaseline
    from rulsafe.report.json import MetricValue

    assert plots.render_plot is not None
    assert baselines.fit_constant_baseline is not None
    with pytest.raises(ValueError, match="evidence"):
        LeakageFinding(
            check_id=LeakageCheckId.FUTURE_IN_FEATURES,
            status=LeakageStatus.PASS,
            evidence=" ",
            remedy="Keep the window causal.",
        )
    finding = LeakageFinding(
        check_id=LeakageCheckId.FUTURE_IN_FEATURES,
        status=LeakageStatus.WARNING,
        evidence="One feature is strongly associated on the training split.",
        remedy="Inspect that feature before trusting it.",
    )
    suite = LeakageSuiteResult(findings=(finding,))
    assert suite.worst_status is LeakageStatus.WARNING
    fitted = FittedBaseline(name=BaselineName.CONSTANT, training_row_count=3)
    assert fitted.training_row_count == 3
    with pytest.raises(ValueError, match="training_row_count"):
        FittedBaseline(name=BaselineName.HIST_GRADIENT_BOOSTING, training_row_count=-1)
    with pytest.raises(ValueError, match="remedy"):
        LeakageFinding(
            check_id=LeakageCheckId.TARGET_IN_FEATURES,
            status=LeakageStatus.PASS,
            evidence="The label column was not in the allowlist.",
            remedy=" ",
        )
    context = AuditContext(protocol_name="group_holdout", censored_policy="report")
    assert context.censored_policy == "report"
    paths = ReportPaths(html_path=None, json_path=None)
    metrics = MetricsReport(
        validation=SplitMetrics(values={"rmse": MetricValue.not_computed()}),
        test=SplitMetrics(values={"rmse": MetricValue.disabled()}),
    )
    result = RunResult(leakage=suite, metrics=metrics, report_paths=paths)
    assert result.report_paths.html_path is None
    with pytest.raises(ValueError, match="must not be empty"):
        TransformerMembership(
            transformer_name=" ",
            split_name="train",
            fitted_row_count=1,
            membership_hash="abc",
            statistics={},
        )
    with pytest.raises(ValueError, match="membership_hash"):
        TransformerMembership(
            transformer_name="scaler",
            split_name="train",
            fitted_row_count=1,
            membership_hash=" ",
            statistics={},
        )
    with pytest.raises(ValueError, match="zero or greater"):
        TransformerMembership(
            transformer_name="scaler",
            split_name="train",
            fitted_row_count=-1,
            membership_hash="abc",
            statistics={},
        )
