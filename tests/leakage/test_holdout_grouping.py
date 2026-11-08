"""Parent-machine grouping must not be silently replaced by episode splitting."""

import csv
from pathlib import Path

import pytest

from rulsafe import run_pipeline
from rulsafe.config import RunConfig
from rulsafe.datasets.synthetic_fleet import CENSORED_ASSET_ID
from rulsafe.exceptions import ConfigurationError


def _episode_config(repository_root: Path, load_example, tmp_path: Path):
    raw = load_example("synthetic_fleet.yaml")
    source = repository_root / "examples/synthetic_fleet"
    with (source / "assets.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    parents = {
        row["asset_id"]: f"machine-{index // 2}"
        for index, row in enumerate(rows)
        if row["asset_id"] != CENSORED_ASSET_ID
    }
    assets = tmp_path / "assets.csv"
    with assets.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["asset_id", "physical_machine_id"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {**row, "physical_machine_id": parents.get(row["asset_id"], "censored-machine")}
            )
    raw["connector"] = {
        "type": "files",
        "assets": str(assets),
        "signals": str(source / "signals.csv"),
        "events": str(source / "events.csv"),
    }
    return raw, parents


def test_stored_parent_group_cannot_reach_fitting(
    repository_root: Path, load_example, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unsupported group set after schema validation stops before model fitting."""
    raw, _parents = _episode_config(repository_root, load_example, tmp_path)
    config = RunConfig.from_mapping(raw)
    holdout = config.split.group_holdout
    assert holdout is not None
    config = config.model_copy(
        update={
            "split": config.split.model_copy(
                update={
                    "group_holdout": holdout.model_copy(
                        update={"group_column": "physical_machine_id"}
                    )
                }
            )
        }
    )

    def forbid_fitting(**_kwargs):
        pytest.fail("Unsupported grouping reached model fitting")

    monkeypatch.setattr("rulsafe.pipeline.execute.fit_constant_baseline", forbid_fitting)
    with pytest.raises(ConfigurationError, match="Use official_partitions"):
        run_pipeline(config, output_directory=tmp_path / "invalid-run")
    assert not (tmp_path / "invalid-run/report.json").exists()


def test_supplied_partitions_keep_all_machine_episodes_together(
    repository_root: Path, load_example, tmp_path: Path
) -> None:
    """Explicit machine-preserving partitions are honored end to end."""
    raw, parents = _episode_config(repository_root, load_example, tmp_path)
    # Two episodes per physical machine. Partition whole machines before
    # writing episode IDs; the library does not infer their parent identity.
    groups = {"train": range(6), "validation": range(6, 8), "test": range(8, 10)}
    partitions = {}
    expected = {}
    for split_name, numbers in groups.items():
        parent_ids = {f"machine-{number}" for number in numbers}
        ids = [episode for episode, parent in parents.items() if parent in parent_ids]
        path = tmp_path / f"{split_name}.txt"
        path.write_text("\n".join(ids) + "\n", encoding="utf-8")
        partitions[f"{split_name}_ids"] = str(path)
        expected[split_name] = set(ids)
    raw["split"] = {"protocol": "official_partitions", "official_partitions": partitions}
    document = run_pipeline(
        RunConfig.from_mapping(raw), output_directory=tmp_path / "grouped-run"
    ).to_dict()
    assert document["status"] == "COMPLETED"
    splits = document["splits"]
    assert {name: set(ids) for name, ids in splits.items()} == expected
    memberships = [{parents[episode] for episode in splits[name]} for name in groups]
    assert memberships[0].isdisjoint(memberships[1])
    assert memberships[0].isdisjoint(memberships[2])
    assert memberships[1].isdisjoint(memberships[2])
    assert all(len(ids) >= 3 for ids in splits.values())
    assert document["censored_or_unsupported_asset_ids"] == [CENSORED_ASSET_ID]
