"""Supervised rows and official last-observation rows.

Features are last, mean, and slope over a causal lookback. The label on a
completed engine is the capped time until failure. An official test engine
is scored at its last observed cycle against the RUL file, and that value
is not written into a training row.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rulsafe.config import RunConfig
from rulsafe.eval.fd001 import cap_remaining_life
from rulsafe.exceptions import ConfigurationError, ContractError
from rulsafe.leakage.fail_on import ObservedWindow
from rulsafe.pipeline.episodes import Episode
from rulsafe.pipeline.features import features_from_windows, lookback_feature_names
from rulsafe.pipeline.labels import assign_remaining_life
from rulsafe.pipeline.windows import build_windows


@dataclass(frozen=True)
class ScoredRow:
    """One prediction and its remaining-life target.

    Attributes:
        asset_id: Equipment identifier.
        prediction_time: Time ``t``.
        features: Causal lookback features.
        remaining_life: Capped target used for fit or score.
    """

    asset_id: str
    prediction_time: float
    features: dict[str, float | None]
    remaining_life: float


@dataclass(frozen=True)
class PreparedExamples:
    """Supervised rows plus the windows and labels the audit reads.

    Attributes:
        rows: Scored rows.
        windows: Windows those rows were built from.
        label_checks: ``(prediction_time, episode_end, label)`` for each row.
        feature_names: Last, mean, and slope names.
    """

    rows: tuple[ScoredRow, ...]
    windows: tuple[ObservedWindow, ...]
    label_checks: tuple[tuple[float, float, float], ...]
    feature_names: tuple[str, ...]


def prepare_supervised(episodes: Sequence[Episode], config: RunConfig) -> PreparedExamples:
    """Build capped causal rows for completed engines.

    Prediction times are strictly before the episode end. ``windows.stride``
    keeps every stride-th time. ``windows.lookback`` limits the past rows.

    Args:
        episodes: Completed histories. Censored histories are not passed here.
        config: Feature, window, and cap settings.

    Returns:
        Rows, windows, and the label triples the future-label check reads.

    Raises:
        ConfigurationError: Feature columns are still unresolved.
        ContractError: A completed history has no end or no remaining life.
    """
    feature_columns = _feature_columns(config)
    feature_names = lookback_feature_names(feature_columns)
    rows: list[ScoredRow] = []
    windows: list[ObservedWindow] = []
    checks: list[tuple[float, float, float]] = []
    for episode in episodes:
        if episode.end_time is None:
            raise ContractError(f"Completed history {episode.asset_id} has no episode end.")
        built = build_windows(
            rows=episode.rows,
            lookback=config.windows.lookback,
            stride=config.windows.stride,
            discard_straddle_split=config.windows.discard_straddle_split,
            prediction_times=_prediction_times(episode),
            gap_policy=config.signals.gap_policy,
            maximum_gap=config.signals.max_gap,
        )
        feature_rows = features_from_windows(built, feature_columns)
        for window, features in zip(built, feature_rows, strict=True):
            prediction_time = _number(window["prediction_time"])
            remaining = assign_remaining_life(
                support=episode.support,
                policy=config.labeling.censored_policy,
                prediction_time=prediction_time,
                episode_end=episode.end_time,
            )
            if remaining is None:
                raise ContractError(f"Completed history {episode.asset_id} has no remaining life.")
            label = cap_remaining_life(remaining, config.target.rul_cap)
            rows.append(
                ScoredRow(
                    asset_id=episode.asset_id,
                    prediction_time=prediction_time,
                    features=features,
                    remaining_life=label,
                )
            )
            windows.append(
                ObservedWindow(
                    prediction_time=prediction_time,
                    end_time=episode.end_time,
                    rows=_window_rows(window),
                )
            )
            checks.append((prediction_time, episode.end_time, label))
    return PreparedExamples(
        rows=tuple(rows),
        windows=tuple(windows),
        label_checks=tuple(checks),
        feature_names=feature_names,
    )


def prepare_official_last_observations(
    episodes: Sequence[Episode],
    truths: Mapping[str, float],
    config: RunConfig,
) -> tuple[tuple[ScoredRow, ...], tuple[ObservedWindow, ...]]:
    """Build one capped row at the last cycle of each official test engine.

    Args:
        episodes: Every history, including censored test engines.
        truths: Official remaining life by asset id, before the cap.
        config: Window and cap settings.

    Returns:
        Scored rows and the windows they came from. These rows are not
        training rows.

    Raises:
        ConfigurationError: An official id has no history or no last window.
    """
    feature_columns = _feature_columns(config)
    by_id = {episode.asset_id: episode for episode in episodes}
    missing = [asset_id for asset_id in truths if asset_id not in by_id]
    if missing:
        listed = ", ".join(sorted(missing))
        raise ConfigurationError(f"Official RUL ids are not in the tables: {listed}.")
    rows: list[ScoredRow] = []
    windows: list[ObservedWindow] = []
    for asset_id in sorted(truths):
        episode = by_id[asset_id]
        if not episode.rows:
            raise ConfigurationError(f"Official engine {asset_id} has no signal rows.")
        last_time = max(_number(row["event_time"]) for row in episode.rows)
        built = build_windows(
            rows=episode.rows,
            lookback=config.windows.lookback,
            stride=1,
            discard_straddle_split=config.windows.discard_straddle_split,
            prediction_times=(last_time,),
            gap_policy=config.signals.gap_policy,
            maximum_gap=config.signals.max_gap,
        )
        if len(built) != 1:
            raise ConfigurationError(
                f"Official engine {asset_id} did not produce its last-observation window."
            )
        features = features_from_windows(built, feature_columns)[0]
        rows.append(
            ScoredRow(
                asset_id=asset_id,
                prediction_time=last_time,
                features=features,
                remaining_life=cap_remaining_life(truths[asset_id], config.target.rul_cap),
            )
        )
        windows.append(
            ObservedWindow(
                prediction_time=last_time,
                end_time=episode.end_time,
                rows=_window_rows(built[0]),
            )
        )
    return tuple(rows), tuple(windows)


def _feature_columns(config: RunConfig) -> tuple[str, ...]:
    """Return the resolved feature allowlist.

    Args:
        config: Run configuration.

    Returns:
        Explicit feature columns.

    Raises:
        ConfigurationError: ``auto`` has not been resolved.
    """
    feature_columns = config.signals.feature_columns
    if not isinstance(feature_columns, list):
        raise ConfigurationError("feature_columns: auto is not resolved in this run yet.")
    return tuple(feature_columns)


def _prediction_times(episode: Episode) -> tuple[float, ...]:
    """Return signal times strictly before the episode end.

    Args:
        episode: One completed history.

    Returns:
        Sorted unique prediction times.
    """
    end_time = episode.end_time
    times = {
        _number(row["event_time"])
        for row in episode.rows
        if end_time is None or _number(row["event_time"]) < end_time
    }
    return tuple(sorted(times))


def _window_rows(window: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    """Read the row tuple stored on a window.

    Args:
        window: One window mapping.

    Returns:
        The causal rows.

    Raises:
        ConfigurationError: The window has no row tuple.
    """
    rows = window.get("rows")
    if isinstance(rows, str) or not isinstance(rows, tuple):
        raise ConfigurationError("A window is missing its rows.")
    mappings: list[Mapping[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ConfigurationError("A window row is not a mapping.")
        mappings.append(row)
    return tuple(mappings)


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
        number = float(value)
    except ValueError as error:
        raise ConfigurationError(f"Expected a number, got {value!r}.") from error
    if not math.isfinite(number):
        raise ConfigurationError(f"Expected a finite number, got {value!r}.")
    return number
