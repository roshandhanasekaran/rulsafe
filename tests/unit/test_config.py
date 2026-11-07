"""Schema tests for the v0.1 completed-trajectory contract."""

from pathlib import Path

import pytest

from rulsafe.config import DEFAULT_FAIL_ON_CHECKS, DEFAULT_WARN_ON_CHECKS, RunConfig
from rulsafe.contract import GapPolicy, parse_gap_policy
from rulsafe.exceptions import ConfigurationError
from rulsafe.models.forbid_persistence import reject_persistence_baseline


def test_completed_trajectory_examples_load(load_example) -> None:
    synthetic = RunConfig.from_mapping(load_example("synthetic_panel.yaml"))
    fleet = RunConfig.from_mapping(load_example("synthetic_fleet.yaml"))
    cmapss = RunConfig.from_mapping(load_example("cmapss_fd001_completed_trajectory.yaml"))
    assert fleet.project.name == "synthetic-fleet"
    assert fleet.labeling.censored_policy.value == "report"
    assert fleet.signals.feature_columns == [
        "temperature",
        "pressure",
        "vibration",
        "flow",
    ]

    assert synthetic.labeling.task.value == "completed_trajectory_rul"
    assert synthetic.labeling.censored_policy.value == "report"
    assert synthetic.split.min_assets_per_split == 3
    assert synthetic.signals.gap_policy is GapPolicy.NONE
    assert tuple(synthetic.models.include) == tuple(cmapss.models.include)
    assert [model.value for model in synthetic.models.include] == [
        "constant",
        "hist_gradient_boosting",
    ]
    assert tuple(synthetic.leakage.fail_on) == DEFAULT_FAIL_ON_CHECKS
    assert tuple(synthetic.leakage.warn_on) == DEFAULT_WARN_ON_CHECKS
    assert cmapss.labeling.task.value == "completed_trajectory_rul"
    assert cmapss.labeling.censored_policy.value == "report"
    assert cmapss.split.protocol.value == "official_partitions"
    assert cmapss.signals.available_at_column is None


def test_scania_task_is_rejected_until_v02(load_example) -> None:
    with pytest.raises(ConfigurationError, match=r"v0\.2"):
        RunConfig.from_mapping(load_example("scania_component_x.yaml"))


def test_silent_censor_policies_are_rejected(load_example) -> None:
    document = load_example("synthetic_panel.yaml")
    labeling = document["labeling"]
    assert isinstance(labeling, dict)
    labeling["unknown_policy"] = "exclude_from_loss"
    with pytest.raises(ConfigurationError, match="never dropped silently"):
        RunConfig.from_mapping(document)

    document = load_example("synthetic_panel.yaml")
    labeling = document["labeling"]
    assert isinstance(labeling, dict)
    labeling["censored_policy"] = "drop"
    with pytest.raises(ConfigurationError, match="would hide histories"):
        RunConfig.from_mapping(document)


def test_horizon_fleet_task_is_rejected(load_example) -> None:
    document = load_example("synthetic_panel.yaml")
    labeling = document["labeling"]
    assert isinstance(labeling, dict)
    labeling["task"] = "failure_within_horizon"
    with pytest.raises(ConfigurationError, match=r"not part of v0\.1"):
        RunConfig.from_mapping(document)


def test_persistence_age_and_logistic_baselines_are_rejected(load_example) -> None:
    for model_name in ("persistence", "rul_persistence", "age", "logistic_regression"):
        candidate = load_example("synthetic_panel.yaml")
        models = candidate["models"]
        assert isinstance(models, dict)
        models["include"] = [model_name]
        with pytest.raises(ConfigurationError):
            RunConfig.from_mapping(candidate)
    with pytest.raises(ConfigurationError, match="Persistence"):
        reject_persistence_baseline("persist_previous_rul")


def test_random_split_and_interpolation_are_rejected(load_example) -> None:
    document = load_example("synthetic_panel.yaml")
    split = document["split"]
    assert isinstance(split, dict)
    split["type"] = "random"
    with pytest.raises(ConfigurationError, match="random"):
        RunConfig.from_mapping(document)

    document = load_example("synthetic_panel.yaml")
    signals = document["signals"]
    assert isinstance(signals, dict)
    signals["gap_policy"] = "linear"
    with pytest.raises(ConfigurationError, match="interpolation"):
        RunConfig.from_mapping(document)
    with pytest.raises(ConfigurationError, match="interpolation"):
        parse_gap_policy("linear_interpolation")


def test_forward_fill_requires_a_positive_max_gap(load_example) -> None:
    document = load_example("synthetic_panel.yaml")
    signals = document["signals"]
    assert isinstance(signals, dict)
    signals["gap_policy"] = "ffill"
    with pytest.raises(ConfigurationError, match="max_gap"):
        RunConfig.from_mapping(document)

    signals["max_gap"] = 3
    loaded = RunConfig.from_mapping(document)
    assert loaded.signals.max_gap == 3


def test_identifiers_and_event_metadata_cannot_be_features(load_example) -> None:
    document = load_example("synthetic_panel.yaml")
    signals = document["signals"]
    assert isinstance(signals, dict)
    signals["feature_columns"] = ["temperature", "asset_id"]
    with pytest.raises(ConfigurationError, match="Identifier"):
        RunConfig.from_mapping(document)

    document = load_example("synthetic_panel.yaml")
    signals = document["signals"]
    assert isinstance(signals, dict)
    signals["feature_columns"] = ["failure_notes"]
    with pytest.raises(ConfigurationError, match="Event metadata"):
        RunConfig.from_mapping(document)

    for column_name in ("remaining_life", "Remaining-Life", "engine_rul"):
        document = load_example("synthetic_panel.yaml")
        signals = document["signals"]
        assert isinstance(signals, dict)
        signals["feature_columns"] = [column_name]
        with pytest.raises(ConfigurationError, match="Target column"):
            RunConfig.from_mapping(document)


def test_warehouse_connector_is_rejected(load_example) -> None:
    document = load_example("synthetic_panel.yaml")
    connector = document["connector"]
    assert isinstance(connector, dict)
    connector["type"] = "snowflake"
    with pytest.raises(ConfigurationError, match="CSV and Parquet"):
        RunConfig.from_mapping(document)


def test_group_ratios_must_sum_to_one(load_example) -> None:
    document = load_example("synthetic_panel.yaml")
    split = document["split"]
    assert isinstance(split, dict)
    holdout = split["group_holdout"]
    assert isinstance(holdout, dict)
    holdout["test_ratio"] = 0.10
    with pytest.raises(ConfigurationError, match="sum to 1"):
        RunConfig.from_mapping(document)


def test_global_time_is_deferred_to_v02(load_example) -> None:
    document = load_example("synthetic_panel.yaml")
    document["split"] = {
        "protocol": "global_time",
        "global_time": {"validation_start": 100, "test_start": 150},
    }
    with pytest.raises(ConfigurationError, match=r"global_time is deferred to v0\.2"):
        RunConfig.from_mapping(document)


def test_alerts_are_deferred_to_v02(load_example) -> None:
    document = load_example("synthetic_panel.yaml")
    evaluation = document["evaluation"]
    assert isinstance(evaluation, dict)
    evaluation["alert"] = {"cadence": "every_row", "cooldown": "horizon"}
    with pytest.raises(ConfigurationError, match=r"alerts are deferred to v0\.2"):
        RunConfig.from_mapping(document)

    document = load_example("synthetic_panel.yaml")
    document["alerts"] = {"cadence": "every_row"}
    with pytest.raises(ConfigurationError, match=r"alerts are deferred to v0\.2"):
        RunConfig.from_mapping(document)

    document = load_example("synthetic_panel.yaml")
    evaluation = document["evaluation"]
    assert isinstance(evaluation, dict)
    evaluation["plots"] = ["alert_lead_times"]
    with pytest.raises(ConfigurationError, match=r"alerts are deferred to v0\.2"):
        RunConfig.from_mapping(document)


def test_load_config_rejects_unusable_files(tmp_path: Path) -> None:
    from rulsafe import load_config

    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="empty"):
        load_config(empty)

    broken = tmp_path / "broken.yaml"
    broken.write_text(":\n  - [", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid YAML"):
        load_config(broken)

    listing = tmp_path / "list.yaml"
    listing.write_text("- just-a-list\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="mapping"):
        load_config(listing)

    with pytest.raises(ConfigurationError, match="Could not read"):
        load_config(tmp_path / "missing.yaml")


def test_unknown_gap_policy_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="Unknown gap policy"):
        parse_gap_policy("backward")


def test_load_config_reads_the_cmapss_example(repository_root: Path) -> None:
    from rulsafe import load_config

    loaded = load_config(repository_root / "examples" / "cmapss_fd001_completed_trajectory.yaml")
    assert loaded.project.name == "cmapss-fd001-completed-trajectory"
    assert "not specified" in loaded.project.notes.lower()
