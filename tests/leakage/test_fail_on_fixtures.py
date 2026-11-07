"""Each fail_on check has a planted CONFIRMED case and a clean PASS control."""

import json
import warnings
from collections.abc import Callable

import pytest

from rulsafe import run_pipeline
from rulsafe.config import LeakageCheckId, LeakageStatus, RunConfig
from rulsafe.exceptions import ContractError
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


def _window(
    prediction_time: float,
    rows: tuple[dict[str, object], ...],
    end_time: float | None = None,
) -> ObservedWindow:
    """Build one window for a leakage fixture."""
    return ObservedWindow(prediction_time=prediction_time, end_time=end_time, rows=rows)


def _signal(event_time: float, available_at: float, asset_id: str = "unit-a") -> dict[str, object]:
    """Build one window row."""
    return {"event_time": event_time, "available_at": available_at, "asset_id": asset_id}


@pytest.mark.parametrize(
    ("clean", "planted"),
    [
        (
            lambda: random_split_finding("group_holdout"),
            lambda: random_split_finding("random"),
        ),
        (
            lambda: future_labels_finding(((0.0, 10.0, 5.0),), 5),
            lambda: future_labels_finding(((0.0, 10.0, 10.0),), 5),
        ),
        (
            lambda: future_in_features_finding((_window(1.0, (_signal(1.0, 1.0),)),)),
            lambda: future_in_features_finding((_window(1.0, (_signal(2.0, 2.0),)),)),
        ),
        (
            lambda: post_event_features_finding(
                (_window(1.0, (_signal(1.0, 1.0),), end_time=5.0),)
            ),
            lambda: post_event_features_finding(
                (_window(5.0, (_signal(4.0, 4.0),), end_time=3.0),)
            ),
        ),
        (
            lambda: delayed_record_finding(
                available_at_supplied=True,
                windows=(_window(2.0, (_signal(1.0, 2.0),)),),
            ),
            lambda: delayed_record_finding(
                available_at_supplied=True,
                windows=(_window(1.0, (_signal(0.0, 4.0),)),),
            ),
        ),
        (
            lambda: interpolation_leak_finding("ffill"),
            lambda: interpolation_leak_finding("linear"),
        ),
        (
            lambda: entity_leakage_finding((_window(1.0, (_signal(1.0, 1.0, "unit-a"),)),)),
            lambda: entity_leakage_finding(
                (_window(1.0, (_signal(1.0, 1.0, "unit-a"), _signal(1.0, 1.0, "unit-b"))),)
            ),
        ),
        (
            lambda: scaler_leakage_finding(("train-a",), ("train-a", "train-b")),
            lambda: scaler_leakage_finding(("train-a", "test-a"), ("train-a",)),
        ),
        (
            lambda: target_in_features_finding(("temperature", "temperature_mean")),
            lambda: target_in_features_finding(("rul_mean",)),
        ),
        (
            lambda: event_metadata_in_features_finding(("temperature",), ("failure_notes",)),
            lambda: event_metadata_in_features_finding(("failure_notes",), ("failure_notes",)),
        ),
        (
            lambda: silent_negative_censoring_finding(("unit-e",), ("unit-a",), ("unit-a",)),
            lambda: silent_negative_censoring_finding(("unit-e",), ("unit-e",), ()),
        ),
        (
            lambda: unsupported_history_finding(("unit-e",), ("unit-e",)),
            lambda: unsupported_history_finding(("unit-e",), ()),
        ),
        (
            lambda: replacement_episode_mix_finding({"unit-a": (0.0, 10.0)}, (("unit-a", 10.0),)),
            lambda: replacement_episode_mix_finding({"unit-a": (0.0, 10.0)}, (("unit-a", 4.0),)),
        ),
        (
            lambda: choice_split_finding("validation", "validation"),
            lambda: choice_split_finding("test", "validation"),
        ),
        (
            lambda: official_hidden_label_finding(
                train_asset_ids=("train-001",),
                official_asset_ids=("test-001",),
                training_used_official_file=False,
            ),
            lambda: official_hidden_label_finding(
                train_asset_ids=("train-001",),
                official_asset_ids=("train-001",),
                training_used_official_file=False,
            ),
        ),
    ],
)
def test_each_fail_on_check_has_a_clean_control_and_a_planted_leak(
    clean: Callable[[], LeakageFinding],
    planted: Callable[[], LeakageFinding],
) -> None:
    """A clean input passes. The planted input is CONFIRMED and names evidence."""
    passed = clean()
    leaked = planted()
    assert passed.status is LeakageStatus.PASS
    assert leaked.status is LeakageStatus.CONFIRMED
    assert leaked.evidence.strip()
    assert leaked.remedy.strip()
    assert passed.check_id is leaked.check_id


def test_missing_available_at_is_not_a_delayed_record_pass() -> None:
    """Without available_at the delayed-record check stays NOT_CHECKED."""
    finding = delayed_record_finding(available_at_supplied=False, windows=())
    assert finding.status is LeakageStatus.NOT_CHECKED
    assert finding.check_id is LeakageCheckId.DELAYED_RECORD_LEAK


def test_confirmed_fail_on_ignores_a_warning_only_check() -> None:
    """Only a CONFIRMED check that is listed in fail_on aborts."""
    confirmed = LeakageFinding(
        check_id=LeakageCheckId.RANDOM_SPLIT,
        status=LeakageStatus.CONFIRMED,
        evidence="A random split was used.",
        remedy="Use a grouped split.",
    )
    warning = LeakageFinding(
        check_id=LeakageCheckId.HIGH_ASSOCIATION_WITH_LABEL,
        status=LeakageStatus.CONFIRMED,
        evidence="One feature tracks the label.",
        remedy="Inspect that feature.",
    )
    assert confirmed_fail_on_ids((confirmed, warning), (LeakageCheckId.RANDOM_SPLIT,)) == (
        "random_split",
    )
    assert confirmed_fail_on_ids((warning,), (LeakageCheckId.RANDOM_SPLIT,)) == ()


def test_planted_fail_on_writes_the_report_then_stops(load_example, tmp_path, monkeypatch) -> None:
    """A CONFIRMED fail_on check leaves a failed report on disk and then raises."""

    def _planted(_protocol: str) -> LeakageFinding:
        return LeakageFinding(
            check_id=LeakageCheckId.RANDOM_SPLIT,
            status=LeakageStatus.CONFIRMED,
            evidence="planted random split",
            remedy="Use a grouped split.",
        )

    monkeypatch.setattr("rulsafe.pipeline.execute.random_split_finding", _planted)
    config = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with pytest.raises(ContractError, match="random_split"):
            run_pipeline(config, output_directory=tmp_path)
    document = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert document["status"] == "FAILED"
    assert document["confirmed_fail_on"] == ["random_split"]
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "FAILED" in html
    assert "Research software" in html
