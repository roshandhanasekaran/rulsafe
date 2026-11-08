"""Exercise RULSafe on physical NASA milling sensor measurements.

This is an opt-in integration smoke check, not an official benchmark or a
milling adapter. Download the NASA archive separately; no data are committed.
Observed flank wear defines the scenario event and is never a feature.
"""

import argparse
import csv
import hashlib
import json
import math
import zipfile
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any

import yaml
from scipy.io import loadmat  # type: ignore[import-untyped]

from rulsafe import run_pipeline
from rulsafe.config import RunConfig
from rulsafe.pipeline.split import partition_in_given_order

ARCHIVE_SHA256 = "bdba8d52ec1a1baab24c2be58480e6ac62508c8cc1f8219f47ebde8fc9ebc474"
INNER_ZIP_SHA256 = "de9c8685cb0e07b4f39459dc282b49192a3ad660e9577ff99b68dc9994e35d27"
MAT_SHA256 = "71486a857939d1416c86c7cf0c469d5e69c7c30495e01ec8a0e13aafd2a313cb"
INNER_ZIP_MEMBER = "3. Milling/mill.zip"
MAT_MEMBER = "mill.mat"
WEAR_THRESHOLD_MM = 0.30
MAX_MEMBER_BYTES = 100_000_000
CHANNELS = {
    "smc_ac": "smcAC",
    "smc_dc": "smcDC",
    "vibration_table": "vib_table",
    "vibration_spindle": "vib_spindle",
    "acoustic_emission_table": "AE_table",
    "acoustic_emission_spindle": "AE_spindle",
}
FEATURES = tuple(f"{channel}_{statistic}" for channel in CHANNELS for statistic in ("mean", "rms"))


def _sha256(content: bytes) -> str:
    """Return the hexadecimal SHA-256 of bytes."""
    return hashlib.sha256(content).hexdigest()


def _member(archive: zipfile.ZipFile, name: str, expected_sha256: str) -> bytes:
    """Read one exact bounded ZIP member and verify its measured digest."""
    matches = [item for item in archive.infolist() if not item.is_dir() and item.filename == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one archive member {name!r}, found {len(matches)}.")
    info = matches[0]
    if info.file_size > MAX_MEMBER_BYTES:
        raise ValueError(f"Archive member {name!r} exceeds the extraction budget.")
    content = archive.read(info)
    if _sha256(content) != expected_sha256:
        raise ValueError(f"Archive member {name!r} differs from the measured NASA source.")
    return content


def _records(archive: Path) -> list[dict[str, Any]]:
    """Read and verify the nested MATLAB source without extracting it."""
    outer_content = archive.read_bytes()
    if _sha256(outer_content) != ARCHIVE_SHA256:
        raise ValueError("Archive SHA-256 differs from the measured NASA source.")
    with zipfile.ZipFile(BytesIO(outer_content)) as outer:
        inner_content = _member(outer, INNER_ZIP_MEMBER, INNER_ZIP_SHA256)
    with zipfile.ZipFile(BytesIO(inner_content)) as inner:
        mat_content = _member(inner, MAT_MEMBER, MAT_SHA256)
    loaded: Any = loadmat(BytesIO(mat_content), simplify_cells=True).get("mill")
    if not isinstance(loaded, list) or not loaded:
        raise ValueError("The measured source does not contain the expected mill records.")
    if not all(isinstance(record, dict) for record in loaded):
        raise ValueError("A mill record is not a mapping.")
    return loaded


def _summaries(record: dict[str, Any]) -> dict[str, float]:
    """Compute two finite summaries of each completed-cut sensor trace."""
    summaries: dict[str, float] = {}
    for public_name, source_name in CHANNELS.items():
        values = [float(value) for value in record[source_name]]
        if not values or not all(math.isfinite(value) for value in values):
            raise ValueError(f"Non-finite or empty sensor values in {source_name}.")
        count = len(values)
        summaries[f"{public_name}_mean"] = math.fsum(values) / count
        summaries[f"{public_name}_rms"] = math.sqrt(
            math.fsum(value * value for value in values) / count
        )
    return summaries


def _tables(archive: Path, directory: Path) -> dict[str, object]:
    """Convert cases into completed or censored component histories."""
    by_case: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in _records(archive):
        by_case[int(record["case"])].append(record)
    if sorted(by_case) != list(range(1, 17)):
        raise ValueError("Expected milling cases 1 through 16.")

    assets: list[dict[str, object]] = []
    signals: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    counts: dict[str, object] = {}
    completed: list[str] = []
    censored: list[str] = []
    for case, unordered in sorted(by_case.items()):
        records = sorted(unordered, key=lambda record: int(record["run"]))
        source_runs = [int(record["run"]) for record in records]
        if len(source_runs) != len(set(source_runs)):
            raise ValueError(f"Milling case {case} repeats a source run number.")
        asset_id = f"case-{case:02d}"
        assets.append({"asset_id": asset_id})
        event_index: int | None = None
        event_source_run: int | None = None
        observed_wear_count = 0
        for index, record in enumerate(records, start=1):
            wear = float(record["VB"])
            if not math.isfinite(wear):
                continue
            observed_wear_count += 1
            if event_index is None and wear >= WEAR_THRESHOLD_MM:
                event_index = index
                event_source_run = int(record["run"])
        stop = event_index if event_index is not None else len(records)
        for index, record in enumerate(records[:stop], start=1):
            signals.append(
                {
                    "asset_id": asset_id,
                    "event_time": index,
                    "available_at": index,
                    **_summaries(record),
                }
            )
        completed_case = event_index is not None
        events.append(
            {
                "asset_id": asset_id,
                "event_time": stop,
                "available_at": stop,
                "event_type": "wear_threshold" if completed_case else "censored_end",
            }
        )
        (completed if completed_case else censored).append(asset_id)
        counts[asset_id] = {
            "source_run_count": len(records),
            "observed_wear_measurement_count": observed_wear_count,
            "first_threshold_observation": event_index,
            "first_threshold_source_run": event_source_run,
        }
    if len(completed) != 15 or censored != ["case-06"]:
        raise ValueError(
            "The measured source should yield 15 completed cases and case-06 censored."
        )

    directory.mkdir(parents=True, exist_ok=True)
    _write_csv(directory / "assets.csv", ["asset_id"], assets)
    _write_csv(
        directory / "signals.csv",
        ["asset_id", "event_time", "available_at", *FEATURES],
        signals,
    )
    _write_csv(
        directory / "events.csv",
        ["asset_id", "event_time", "available_at", "event_type"],
        events,
    )
    split = partition_in_given_order(completed)
    for name, identifiers in split.items():
        (directory / f"{name.value}.txt").write_text(
            "\n".join(identifiers) + "\n", encoding="utf-8"
        )
    return {
        "cases": counts,
        "completed_case_count": len(completed),
        "censored_case_ids": censored,
        "partitions": {name.value: list(identifiers) for name, identifiers in split.items()},
    }


def _write_csv(
    path: Path,
    fields: list[str] | tuple[str, ...],
    rows: list[dict[str, object]],
) -> None:
    """Write one local input table."""
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    """Convert the pinned local archive and run the existing RUL pipeline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, default=Path("rulsafe-runs/nasa-milling"))
    args = parser.parse_args()
    output = args.output.resolve()
    inputs = output / "inputs"
    source_summary = _tables(args.archive, inputs)

    repository = Path(__file__).resolve().parents[1]
    raw = yaml.safe_load(
        (repository / "examples" / "synthetic_fleet.yaml").read_text(encoding="utf-8")
    )
    raw["project"]["name"] = "nasa-milling-physical-smoke"
    raw["project"]["notes"] = (
        "Physical milling integration check; user-defined wear threshold, not a benchmark."
    )
    raw["connector"] = {
        "type": "files",
        "assets": str(inputs / "assets.csv"),
        "signals": str(inputs / "signals.csv"),
        "events": str(inputs / "events.csv"),
    }
    raw["signals"]["feature_columns"] = list(FEATURES)
    raw["events"]["terminal_types"] = ["wear_threshold"]
    raw["events"]["competing_types"] = ["censored_end"]
    raw["events"]["forbidden_as_features"] = ["flank_wear", "VB"]
    raw["labeling"]["unit"] = "steps"
    raw["split"] = {
        "protocol": "official_partitions",
        "official_partitions": {
            f"{name}_ids": str(inputs / f"{name}.txt") for name in ("train", "validation", "test")
        },
    }
    raw["report"]["title"] = "NASA milling physical-data smoke check"
    (output / "run.yaml").write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    result = run_pipeline(RunConfig.from_mapping(raw), output_directory=output)
    document = result.to_dict()
    if document["censored_or_unsupported_asset_ids"] != ["case-06"]:
        raise ValueError("The case without an observed wear threshold must stay censored.")
    summary = {
        "source": {
            "archive_sha256": ARCHIVE_SHA256,
            "inner_zip_sha256": INNER_ZIP_SHA256,
            "mat_sha256": MAT_SHA256,
        },
        "wear_threshold_mm": WEAR_THRESHOLD_MM,
        **source_summary,
        "status": document["status"],
        "splits": document["splits"],
        "metrics": document["metrics"],
        "risks": document["risks"],
        "leakage": document["leakage"],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
