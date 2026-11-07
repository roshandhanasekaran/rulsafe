"""Deterministic noisy fleet for the synthetic demo.

The unit smoke panel under ``tests/fixtures/synthetic_panel`` fails every
engine at the same time, and one sensor is the time index, so remaining life
is a rearrangement of that sensor. This fleet is the demo instead: lifetimes
differ, four sensors drift and carry fixed noise, and a censored unit is left
out of every split. The same function always writes the same files.
"""

from collections.abc import Sequence
from pathlib import Path

COMPLETED_ASSET_COUNT = 20
SENSORS: tuple[str, ...] = ("temperature", "pressure", "vibration", "flow")
CENSORED_ASSET_ID = "unit-censored"
_CENSORED_CYCLES = 6


def completed_asset_id(index: int) -> str:
    """Return the id of one completed unit.

    Args:
        index: One-based unit number from 1 to ``COMPLETED_ASSET_COUNT``.

    Returns:
        ``unit-01`` style identifier.
    """
    return f"unit-{index:02d}"


def lifetime_cycles(index: int) -> int:
    """Return the failure cycle of one completed unit.

    Args:
        index: One-based unit number.

    Returns:
        Failure cycle. The values are not all equal.
    """
    return 8 + ((index * 5) % 13)


def fleet_tables() -> tuple[str, str, str]:
    """Build the assets, signals, and events CSV text.

    Returns:
        Three CSV documents, each ending in a newline. Asset order is the
        completed units, then the censored unit.
    """
    assets = [
        "asset_id",
        *[completed_asset_id(index) for index in range(1, COMPLETED_ASSET_COUNT + 1)],
    ]
    assets.append(CENSORED_ASSET_ID)
    signal_rows: list[str] = [
        "asset_id,event_time,available_at,temperature,pressure,vibration,flow"
    ]
    event_rows: list[str] = ["asset_id,event_time,available_at,event_type,failure_notes"]
    for index in range(1, COMPLETED_ASSET_COUNT + 1):
        asset_id = completed_asset_id(index)
        life = lifetime_cycles(index)
        for cycle in range(life + 1):
            signal_rows.append(_signal_line(asset_id, index, cycle, life))
        event_rows.append(f"{asset_id},{life},{life},failure,wear")
    for cycle in range(_CENSORED_CYCLES + 1):
        signal_rows.append(_signal_line(CENSORED_ASSET_ID, 0, cycle, _CENSORED_CYCLES))
    event_rows.append(
        f"{CENSORED_ASSET_ID},{_CENSORED_CYCLES},{_CENSORED_CYCLES},censored_end,left-study"
    )
    return _as_csv(assets), _as_csv(signal_rows), _as_csv(event_rows)


def write_fleet(directory: Path) -> None:
    """Write the three fleet CSV files into ``directory``.

    Args:
        directory: Destination directory. It is created when missing.
    """
    directory.mkdir(parents=True, exist_ok=True)
    assets, signals, events = fleet_tables()
    (directory / "assets.csv").write_text(assets, encoding="utf-8")
    (directory / "signals.csv").write_text(signals, encoding="utf-8")
    (directory / "events.csv").write_text(events, encoding="utf-8")


def _signal_line(asset_id: str, index: int, cycle: int, life: int) -> str:
    """Format one signal row.

    Args:
        asset_id: Equipment identifier.
        index: Unit number used by the noise formula. Zero is the censored unit.
        cycle: Observation cycle.
        life: Failure or censor cycle used as the drift horizon.

    Returns:
        One CSV line without a trailing newline.
    """
    values = [_sensor_value(index, cycle, life, channel) for channel in range(len(SENSORS))]
    rendered = ",".join(f"{value:.4f}" for value in values)
    return f"{asset_id},{cycle},{cycle},{rendered}"


def _sensor_value(index: int, cycle: int, life: int, channel: int) -> float:
    """Return one drifted, noisy sensor value.

    Args:
        index: Unit number.
        cycle: Observation cycle.
        life: Horizon that scales the drift. A longer life reaches the same
            progress more slowly, so the value is not a function of remaining life.
        channel: Sensor index into ``SENSORS``.

    Returns:
        The sensor value.
    """
    progress = 0.0 if life == 0 else cycle / life
    if channel == 0:
        baseline = 40.0 + 55.0 * progress
    elif channel == 1:
        baseline = 12.0 + 8.0 * progress + 6.0 * progress * progress
    elif channel == 2:
        baseline = 0.4 + 2.4 * progress * progress
    else:
        baseline = 90.0 - 28.0 * progress
    return baseline + _noise(index, cycle, channel)


def _noise(index: int, cycle: int, channel: int) -> float:
    """Return fixed noise in ``[-0.6, 0.6]``.

    Args:
        index: Unit number.
        cycle: Observation cycle.
        channel: Sensor index.

    Returns:
        The noise term. It does not use a random generator.
    """
    raw = (index * 17 + cycle * 13 + channel * 29) % 9 - 4
    return raw * 0.15


def _as_csv(lines: Sequence[str]) -> str:
    """Join CSV lines and end the document with a newline.

    Args:
        lines: Header and body lines, without trailing newlines.

    Returns:
        The CSV document.
    """
    return "\n".join(lines) + "\n"
