"""Offline FD001 conversion. These tests do not use the network."""

import hashlib
import urllib.error
import urllib.request
import warnings
import zipfile
from pathlib import Path

import pytest

from rulsafe import run_pipeline
from rulsafe.config import RunConfig
from rulsafe.contract import LogicalTableRole
from rulsafe.datasets.cmapss_convert import (
    CMAPSS_ARCHIVE_URL,
    CMAPSS_INNER_SHA256,
    CMAPSS_OUTER_SHA256,
    _download_archive,
    convert_fd001_archive,
    fetch_cmapss_fd001,
)
from rulsafe.exceptions import ConfigurationError
from rulsafe.io.files import load_table
from rulsafe.pipeline.split import (
    assign_official_partitions,
    partition_in_given_order,
    read_split_ids,
)


def test_pinned_nasa_hashes_and_source_url() -> None:
    """The fetch command is locked to the Prognostics outer zip and the inner archive."""
    assert CMAPSS_ARCHIVE_URL == (
        "https://phm-datasets.s3.amazonaws.com/NASA/"
        "6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip"
    )
    assert CMAPSS_OUTER_SHA256 == "c9c5dec12a945a82e8bb4446589d7fb3cc057b5e5d81fa1a12e25ee9912ad3b2"
    assert CMAPSS_INNER_SHA256 == "74bef434a34db25c7bf72e668ea4cd52afe5f2cf8e44367c55a82bfd91a5a34f"


def test_completed_engines_use_unit_order_without_a_shuffle() -> None:
    """One hundred completed engines become 70, 15, and 15 in unit-number order."""
    identifiers = tuple(f"train-{unit:03d}" for unit in range(1, 101))
    split = partition_in_given_order(identifiers)
    assert len(split["train"]) == 70
    assert len(split["validation"]) == 15
    assert len(split["test"]) == 15
    assert split["train"][0] == "train-001"
    assert split["validation"][0] == "train-071"
    assert split["test"][0] == "train-086"


def test_convert_writes_censored_test_engines_and_the_official_rul_file(tmp_path: Path) -> None:
    """A tiny FD001 zip becomes tables. The RUL file is test truth, not a feature."""
    archive = tmp_path / "CMAPSSData.zip"
    _write_fd001_zip(archive)
    destination = tmp_path / "cmapss"
    counts = convert_fd001_archive(archive, destination)
    assert counts == {
        "completed_engines": 10,
        "censored_engines": 2,
        "train_engines": 7,
        "validation_engines": 2,
        "test_engines": 1,
    }
    events = load_table(destination / "fd001_events.parquet", LogicalTableRole.EVENTS)
    by_id = {row["unit_id"]: row["event_type"] for row in events.rows}
    assert by_id["train-001"] == "failure"
    assert by_id["test-001"] == "censored"
    signals = load_table(destination / "fd001_signals.parquet", LogicalTableRole.SIGNALS)
    assert all("424242" not in row.values() for row in signals.rows)
    rul_lines = (destination / "fd001_official_rul.txt").read_text(encoding="utf-8").splitlines()
    assert rul_lines == ["test-001 424242", "test-002 424242"]
    train_ids = (destination / "fd001_train_ids.txt").read_text(encoding="utf-8").split()
    assert train_ids == [f"train-{unit:03d}" for unit in range(1, 8)]
    assert "test-001" not in train_ids


def test_outer_zip_is_unwrapped_only_when_both_hashes_match(tmp_path: Path) -> None:
    """A local outer zip is accepted when its hash and the inner hash are the ones supplied."""
    inner = tmp_path / "CMAPSSData.zip"
    _write_fd001_zip(inner, member_prefix="nested/")
    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as bundle:
        bundle.write(inner, arcname="folder/CMAPSSData.zip")
    destination = tmp_path / "out"
    fetch_cmapss_fd001(
        destination,
        archive=outer,
        outer_sha256=_digest(outer),
        inner_sha256=_digest(inner),
    )
    assert (destination / "fd001_assets.parquet").is_file()
    with pytest.raises(ConfigurationError, match="SHA-256 mismatch"):
        fetch_cmapss_fd001(
            tmp_path / "rejected",
            archive=outer,
            outer_sha256="0" * 64,
            inner_sha256=_digest(inner),
        )
    assert not (tmp_path / "rejected").exists()


def test_converted_fixture_runs_the_completed_trajectory_pipeline(
    load_example, tmp_path: Path
) -> None:
    """Official id files score only the completed engines. Censored test engines stay out."""
    archive = tmp_path / "CMAPSSData.zip"
    _write_fd001_zip(archive)
    tables = tmp_path / "tables"
    convert_fd001_archive(archive, tables)
    raw = load_example("cmapss_fd001_completed_trajectory.yaml")
    connector = raw["connector"]
    assert isinstance(connector, dict)
    raw["connector"] = {
        **connector,
        "assets": str(tables / "fd001_assets.parquet"),
        "signals": str(tables / "fd001_signals.parquet"),
        "events": str(tables / "fd001_events.parquet"),
    }
    split = raw["split"]
    assert isinstance(split, dict)
    partitions = split["official_partitions"]
    assert isinstance(partitions, dict)
    raw["split"] = {
        **split,
        "official_partitions": {
            "train_ids": str(tables / "fd001_train_ids.txt"),
            "validation_ids": str(tables / "fd001_validation_ids.txt"),
            "test_ids": str(tables / "fd001_test_ids.txt"),
        },
    }
    evaluation = raw["evaluation"]
    assert isinstance(evaluation, dict)
    raw["evaluation"] = {
        **evaluation,
        "official_benchmark": {
            "protocol": "fd001_last_observation",
            "rul_path": str(tables / "fd001_official_rul.txt"),
        },
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        document = run_pipeline(
            RunConfig.from_mapping(raw), output_directory=tmp_path / "run"
        ).to_dict()
    assert document["status"] == "COMPLETED"
    censored = document["censored_or_unsupported_asset_ids"]
    assert censored == ["test-001", "test-002"]
    splits = document["splits"]
    assert isinstance(splits, dict)
    assert len(splits["train"]) == 7
    assert len(splits["validation"]) == 2
    assert len(splits["test"]) == 1
    assert "test-001" not in splits["train"] + splits["validation"] + splits["test"]
    metrics = document["metrics"]
    assert isinstance(metrics, dict)
    for split_name in ("validation", "test"):
        block = metrics[split_name]
        assert isinstance(block, dict)
        for name in (
            "constant_root_mean_square_error",
            "hist_gradient_boosting_root_mean_square_error",
            "hist_gradient_boosting_nasa_score",
        ):
            metric = block[name]
            assert isinstance(metric, dict)
            assert metric["status"] == "COMPUTED"
    report_text = (tmp_path / "run" / "report.json").read_text(encoding="utf-8")
    assert "424242" not in report_text
    html_text = (tmp_path / "run" / "report.html").read_text(encoding="utf-8")
    assert "424242" not in html_text
    assert document["rul_cap"] == 125
    official = document["official_benchmark"]
    assert isinstance(official, dict)
    assert official["protocol"] == "fd001_last_observation"
    assert official["test"]["engine_count"] == 2
    secondary = document["secondary_evaluation"]
    assert isinstance(secondary, dict)
    assert secondary["role"] == "secondary"
    assert "test-001" not in document["splits"]["train"]


def test_download_and_archive_errors_stay_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The downloader and the zip checks fail closed without contacting NASA."""
    with pytest.raises(ConfigurationError, match="https"):
        _download_archive("http://example.test/cmapss.zip", tmp_path / "nope.zip")

    class _Body:
        def __enter__(self) -> "_Body":
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def read(self) -> bytes:
            return b"pinned-bytes"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: _Body())
    saved = tmp_path / "saved.zip"
    _download_archive("https://example.test/cmapss.zip", saved)
    assert saved.read_bytes() == b"pinned-bytes"

    def reject_url(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", reject_url)
    with pytest.raises(ConfigurationError, match="timed out"):
        _download_archive("https://example.test/cmapss.zip", tmp_path / "failed.zip")

    inner = tmp_path / "CMAPSSData.zip"
    _write_fd001_zip(inner)
    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as bundle:
        bundle.write(inner, arcname="CMAPSSData.zip")

    def copy_outer(url: str, destination: Path) -> None:
        assert url == "https://example.test/outer.zip"
        destination.write_bytes(outer.read_bytes())

    monkeypatch.setattr("rulsafe.datasets.cmapss_convert._download_archive", copy_outer)
    fetch_cmapss_fd001(
        tmp_path / "downloaded",
        url="https://example.test/outer.zip",
        outer_sha256=_digest(outer),
        inner_sha256=_digest(inner),
    )
    with pytest.raises(ConfigurationError, match="SHA-256 mismatch"):
        fetch_cmapss_fd001(
            tmp_path / "bad-inner",
            archive=outer,
            outer_sha256=_digest(outer),
            inner_sha256="ab" * 32,
        )
    fetch_cmapss_fd001(
        tmp_path / "from-inner",
        archive=inner,
        outer_sha256=_digest(outer),
        inner_sha256=_digest(inner),
    )
    plain = tmp_path / "notes.txt"
    plain.write_text("hello", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="not a zip"):
        convert_fd001_archive(plain, tmp_path / "unused")
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as bundle:
        bundle.writestr("readme.txt", "hi")
    with pytest.raises(ConfigurationError, match="missing FD001"):
        convert_fd001_archive(empty, tmp_path / "unused")
    with pytest.raises(ConfigurationError, match="columns"):
        _convert_text(tmp_path / "short", train="1 1\n", test=_trajectory(range(1, 3), cycles=3))
    bad_unit = _trajectory(range(1, 11), cycles=4).replace("1 ", "x ", 1)
    with pytest.raises(ConfigurationError, match="not an integer"):
        _convert_text(tmp_path / "unit", train=bad_unit, test=_trajectory(range(1, 3), cycles=3))
    with pytest.raises(ConfigurationError, match="one value per"):
        _convert_text(
            tmp_path / "rul",
            train=_trajectory(range(1, 11), cycles=4),
            test=_trajectory(range(1, 3), cycles=3),
            rul="424242\n",
        )
    with pytest.raises(ConfigurationError, match="at least one asset"):
        partition_in_given_order(("train-001", "train-002"))
    blank = tmp_path / "blank.txt"
    blank.write_text("\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="no asset ids"):
        read_split_ids(blank)
    repeated = tmp_path / "repeated.txt"
    repeated.write_text("train-001\ntrain-001\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="repeats"):
        read_split_ids(repeated)
    with pytest.raises(ConfigurationError, match="Could not read split"):
        read_split_ids(tmp_path / "absent.txt")
    with pytest.raises(ConfigurationError, match="more than one official"):
        assign_official_partitions(
            ("train-001",),
            train_ids=("train-001",),
            validation_ids=("train-001",),
            test_ids=("train-002",),
        )
    with pytest.raises(ConfigurationError, match="Missing"):
        assign_official_partitions(
            ("train-001", "train-002"),
            train_ids=("train-001",),
            validation_ids=("train-003",),
            test_ids=("train-004",),
        )


def _convert_text(directory: Path, *, train: str, test: str, rul: str = "1\n1\n") -> None:
    archive = directory.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("train_FD001.txt", train)
        bundle.writestr("test_FD001.txt", test)
        bundle.writestr("RUL_FD001.txt", rul)
    convert_fd001_archive(archive, directory)


def _write_fd001_zip(path: Path, *, member_prefix: str = "") -> None:
    members = {
        f"{member_prefix}train_FD001.txt": _trajectory(range(1, 11), cycles=4),
        f"{member_prefix}test_FD001.txt": _trajectory(range(1, 3), cycles=3),
        f"{member_prefix}RUL_FD001.txt": "424242\n424242\n",
    }
    with zipfile.ZipFile(path, "w") as bundle:
        for name, text in members.items():
            bundle.writestr(name, text)


def _trajectory(units: range, *, cycles: int) -> str:
    lines: list[str] = []
    for unit in units:
        for cycle in range(1, cycles + 1):
            cells = [str(unit), str(cycle), "0.1", "0.2", "0.3"]
            cells.extend(str(unit * 10 + cycle) for _index in range(21))
            lines.append(" ".join(cells))
    return "\n".join(lines) + "\n"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
