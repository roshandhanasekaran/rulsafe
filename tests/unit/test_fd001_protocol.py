"""FD001 protocol pieces: cap, per-engine NASA score, bootstrap, and HTML."""

from pathlib import Path

import pytest

from rulsafe.config import RunConfig
from rulsafe.eval.bootstrap import bootstrap_engine_intervals
from rulsafe.eval.fd001 import cap_remaining_life, protocol_description, read_official_rul
from rulsafe.eval.metrics import nasa_asymmetric_score, score_with_per_engine_nasa
from rulsafe.exceptions import ConfigurationError, ContractError
from rulsafe.report.html import render_html, write_html_report


def test_piecewise_cap_is_min_and_the_default_is_unchanged() -> None:
    """A cap of 125 leaves a short life alone and cuts a long one."""
    assert cap_remaining_life(40.0, None) == 40.0
    assert cap_remaining_life(40.0, 125) == 40.0
    assert cap_remaining_life(200.0, 125) == 125.0


def test_rul_cap_rejects_a_non_positive_value(load_example) -> None:
    """Zero and a negative cap are configuration errors."""
    raw = load_example("synthetic_fleet.yaml")
    raw["target"] = {"rul_cap": 0}
    with pytest.raises(ConfigurationError, match="rul_cap"):
        RunConfig.from_mapping(raw)


def test_official_rul_file_is_asset_and_value(tmp_path: Path) -> None:
    """The converted RUL file is joined by asset id and rejects a bad line."""
    path = tmp_path / "fd001_official_rul.txt"
    path.write_text("test-001 112\n\ntest-002 98\n", encoding="utf-8")
    assert read_official_rul(path) == {"test-001": 112.0, "test-002": 98.0}
    path.write_text("112\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="asset id"):
        read_official_rul(path)
    with pytest.raises(ConfigurationError, match="not on disk"):
        read_official_rul(tmp_path / "missing.txt")
    path.write_text("test-001 1\ntest-001 2\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="repeats"):
        read_official_rul(path)
    path.write_text("test-001 later\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="non-numeric"):
        read_official_rul(path)
    path.write_text("test-001 nan\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="non-finite"):
        read_official_rul(path)
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="no rows"):
        read_official_rul(path)


def test_nasa_score_uses_the_last_row_of_each_engine() -> None:
    """Earlier rows change RMSE and do not add another NASA term."""
    scored = score_with_per_engine_nasa(
        asset_ids=("engine-a", "engine-a"),
        times=(1.0, 2.0),
        actual=(0.0, 0.0),
        predicted=(10.0, 0.0),
    )
    assert scored["nasa_score"].value == 0.0
    assert scored["root_mean_square_error"].value is not None
    assert scored["root_mean_square_error"].value > 0.0
    per_row = nasa_asymmetric_score((0.0, 0.0), (10.0, 0.0))
    assert per_row > 0.0


def test_bootstrap_intervals_are_deterministic_and_cover_the_point() -> None:
    """Resampling engines repeats for a seed, and one engine collapses the interval."""
    wide = bootstrap_engine_intervals(
        asset_ids=("a", "a", "b"),
        actual=(0.0, 0.0, 0.0),
        predicted=(0.0, 2.0, 8.0),
        seed=7,
        samples=40,
    )
    again = bootstrap_engine_intervals(
        asset_ids=("a", "a", "b"),
        actual=(0.0, 0.0, 0.0),
        predicted=(0.0, 2.0, 8.0),
        seed=7,
        samples=40,
    )
    assert wide == again
    rmse = wide["root_mean_square_error"]
    assert isinstance(rmse, dict)
    assert rmse["lower"] <= rmse["point"] <= rmse["upper"]
    single = bootstrap_engine_intervals(
        asset_ids=("only",),
        actual=(3.0,),
        predicted=(5.0,),
        seed=1,
        samples=8,
    )
    single_rmse = single["root_mean_square_error"]
    assert isinstance(single_rmse, dict)
    assert single_rmse["lower"] == single_rmse["point"] == single_rmse["upper"]
    with pytest.raises(ContractError, match="at least one"):
        bootstrap_engine_intervals(asset_ids=(), actual=(), predicted=(), seed=1)
    with pytest.raises(ContractError, match="at least 1"):
        bootstrap_engine_intervals(
            asset_ids=("a",), actual=(1.0,), predicted=(1.0,), seed=1, samples=0
        )
    with pytest.raises(ContractError, match="between 0 and 1"):
        bootstrap_engine_intervals(
            asset_ids=("a",), actual=(1.0,), predicted=(1.0,), seed=1, level=0.0
        )
    with pytest.raises(ContractError, match="same length"):
        bootstrap_engine_intervals(asset_ids=("a",), actual=(1.0,), predicted=(), seed=1)
    exact = bootstrap_engine_intervals(
        asset_ids=("a", "b"),
        actual=(0.0, 0.0),
        predicted=(1.0, 3.0),
        seed=3,
        samples=41,
    )
    exact_rmse = exact["root_mean_square_error"]
    assert isinstance(exact_rmse, dict)
    assert exact_rmse["lower"] <= exact_rmse["upper"]


def test_protocol_text_names_the_cap_and_the_official_truth() -> None:
    """The report paragraph states the cap and which view is official."""
    official = protocol_description(official=True, rul_cap=125)
    generic = protocol_description(official=False, rul_cap=None)
    assert "RUL_FD001.txt" in official
    assert "125" in official
    assert "secondary" in official
    assert "one term per engine" in official
    assert "null" not in official
    assert "none" in generic
    assert "No official FD001" in generic


def test_html_report_escapes_text_and_states_the_disclaimer(tmp_path: Path) -> None:
    """The HTML file is self-contained and does not treat a name as markup."""
    document = {
        "title": "Configured <report>",
        "project": "<script>alert(1)</script>",
        "status": "COMPLETED",
        "disclaimer": (
            "Research software, not a safety-certified prognostic. "
            "A listed pass is not a guarantee that every leak was checked."
        ),
        "headline_model": "hist_gradient_boosting",
        "headline_split": "test",
        "rul_cap": 125,
        "selection_split": "validation",
        "evaluation_protocol": {
            "name": "fd001_last_observation",
            "nasa_score": "one term per engine",
            "description": "Last observation against RUL_FD001.txt.",
        },
        "headline_metrics": {"model": "hist_gradient_boosting", "root_mean_square_error": 1.5},
        "confidence_intervals": {
            "method": "percentile bootstrap over engines",
            "samples": 1000,
            "level": 0.95,
            "seed": 7,
            "headline_test": {
                "status": "COMPUTED",
                "models": {
                    "constant": {
                        "root_mean_square_error": {"point": 2.0, "lower": 1.0, "upper": 3.0},
                        "mean_absolute_error": {"point": 1.5, "lower": 1.0, "upper": 2.0},
                    }
                },
            },
        },
        "leakage": [
            {
                "check_id": "future_in_features",
                "status": "PASS",
                "evidence": "Past rows only.",
                "remedy": "Keep the filter.",
            }
        ],
    }
    html = render_html(document)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<title>Configured &lt;report&gt;</title>" in html
    assert "Research software" in html
    assert "not a guarantee" in html
    assert "fd001_last_observation" in html
    assert "125" in html
    assert "1000" in html
    path = write_html_report(document, tmp_path / "report.html")
    assert path.read_text(encoding="utf-8") == html
    assert "http://" not in html
