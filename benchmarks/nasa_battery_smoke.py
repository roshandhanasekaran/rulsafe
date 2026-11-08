"""Exercise the generic CSV pipeline on physical NASA battery aging data.

This is an opt-in integration smoke check, not an official benchmark or a
battery adapter. Download the NASA archive separately; no data are committed.
Capacity defines the documented end-of-life event and is never a feature.
"""

import argparse
import csv
import hashlib
import json
import math
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import yaml
from scipy.io import loadmat  # type: ignore[import-untyped]

from rulsafe import run_pipeline
from rulsafe.config import RunConfig

ARCHIVE_SHA256 = "82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e"
CELLS = ("B0005", "B0006", "B0007", "B0018")
CHANNELS = {
    "voltage": "Voltage_measured",
    "current": "Current_measured",
    "temperature": "Temperature_measured",
}


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    """Write one local input table."""
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _tables(archive: Path, directory: Path) -> dict[str, object]:
    """Convert only the first study's four cells and keep censored histories."""
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Archive SHA-256 differs from the measured NASA source.")
    signals: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    counts: dict[str, object] = {}
    with zipfile.ZipFile(archive) as outer:
        member = "5. Battery Data Set/1. BatteryAgingARC-FY08Q4.zip"
        with zipfile.ZipFile(BytesIO(outer.read(member))) as inner:
            for cell in CELLS:
                data: Any = loadmat(BytesIO(inner.read(f"{cell}.mat")), simplify_cells=True)
                cycles = [cycle for cycle in data[cell]["cycle"] if cycle["type"] == "discharge"]
                end = next(
                    (
                        index
                        for index, cycle in enumerate(cycles, 1)
                        if float(cycle["data"]["Capacity"]) <= 1.4
                    ),
                    None,
                )
                # Every summary is knowable at the end of that discharge. Later
                # cycles are discarded once EOL is observed. No capacity or
                # cycle duration enters the sensor feature table.
                stop = end if end is not None else len(cycles)
                for index, cycle in enumerate(cycles[:stop], 1):
                    row: dict[str, object] = {
                        "asset_id": cell,
                        "event_time": index,
                        "available_at": index,
                    }
                    for feature, channel in CHANNELS.items():
                        values = [float(value) for value in cycle["data"][channel]]
                        if not values or not all(math.isfinite(value) for value in values):
                            raise ValueError(f"Non-finite or empty sensor values in {cell}.")
                        row[feature] = sum(values) / len(values)
                    signals.append(row)
                events.append(
                    {
                        "asset_id": cell,
                        "event_time": stop,
                        "available_at": stop,
                        "event_type": "failure" if end is not None else "censored_end",
                    }
                )
                counts[cell] = {"observed_discharges": len(cycles), "first_eol_discharge": end}
    directory.mkdir(parents=True, exist_ok=True)
    _write_csv(directory / "assets.csv", ["asset_id"], [{"asset_id": cell} for cell in CELLS])
    _write_csv(
        directory / "signals.csv",
        ["asset_id", "event_time", "available_at", *CHANNELS],
        signals,
    )
    _write_csv(
        directory / "events.csv",
        ["asset_id", "event_time", "available_at", "event_type"],
        events,
    )
    return counts


def main() -> None:
    """Convert the pinned local archive and run the existing RUL pipeline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, default=Path("rulsafe-runs/nasa-battery"))
    args = parser.parse_args()
    output = args.output.resolve()
    inputs = output / "inputs"
    counts = _tables(args.archive, inputs)
    repo = Path(__file__).resolve().parents[1]
    raw = yaml.safe_load((repo / "examples/synthetic_fleet.yaml").read_text(encoding="utf-8"))
    raw["project"]["name"] = "nasa-battery-physical-smoke"
    raw["project"]["notes"] = "Physical battery integration check; custom split, not a benchmark."
    raw["connector"] = {
        "type": "files",
        **{
            key: str(inputs / filename)
            for key, filename in (
                ("assets", "assets.csv"),
                ("signals", "signals.csv"),
                ("events", "events.csv"),
            )
        },
    }
    raw["signals"]["feature_columns"] = list(CHANNELS)
    # Chosen by ascending completed-cell ID, not by model scores. This is a
    # manual smoke split, not a NASA or literature evaluation protocol.
    for name, cell in (("train", "B0005"), ("validation", "B0006"), ("test", "B0018")):
        (inputs / f"{name}.txt").write_text(cell + "\n", encoding="utf-8")
    raw["split"] = {
        "protocol": "official_partitions",
        "official_partitions": {
            f"{name}_ids": str(inputs / f"{name}.txt") for name in ("train", "validation", "test")
        },
    }
    (output / "run.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    result = run_pipeline(RunConfig.from_mapping(raw), output_directory=output)
    document = result.to_dict()
    if document["censored_or_unsupported_asset_ids"] != ["B0007"]:
        raise ValueError("The unreached EOL cell must stay censored and excluded.")
    summary = {
        "source_sha256": ARCHIVE_SHA256,
        "cells": counts,
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
