"""Fail-on leakage checks.

Each function returns ``PASS`` or ``CONFIRMED`` from the rows it is given.
``delayed_record_leak`` returns ``NOT_CHECKED`` when ``available_at`` was not
supplied. ``high_association_with_label`` returns ``WARNING`` when a training
feature tracks the target. A planted input is how the tests show
``CONFIRMED``. The pipeline passes the windows, labels, and fit records it
actually used.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rulsafe.config import LeakageCheckId, LeakageStatus
from rulsafe.contract import column_is_target_name
from rulsafe.exceptions import ConfigurationError
from rulsafe.leakage.checks import LeakageFinding

_INTERPOLATION_POLICIES = frozenset(
    {"linear", "interpolate", "interpolation", "linear_interpolation", "interp"}
)
_FEATURE_SUFFIXES = ("_mean", "_slope")


@dataclass(frozen=True)
class ObservedWindow:
    """One window the model was allowed to see.

    Attributes:
        prediction_time: Time ``t``.
        end_time: Episode end, when the history has one.
        rows: Rows placed in the window.
    """

    prediction_time: float
    end_time: float | None
    rows: tuple[Mapping[str, object], ...]


def random_split_finding(protocol: str) -> LeakageFinding:
    """Confirm a random row split.

    Args:
        protocol: Split protocol name.

    Returns:
        ``CONFIRMED`` when the protocol is ``random``.
    """
    if protocol == "random":
        return _finding(
            LeakageCheckId.RANDOM_SPLIT,
            LeakageStatus.CONFIRMED,
            f"Split protocol is {protocol}.",
            "Use group_holdout or official_partitions. Do not shuffle panel rows.",
        )
    return _finding(
        LeakageCheckId.RANDOM_SPLIT,
        LeakageStatus.PASS,
        f"Split protocol is {protocol}.",
        "Keep a named protocol. Do not shuffle panel rows.",
    )


def future_labels_finding(
    rows: Sequence[tuple[float, float, float]],
    rul_cap: int | None,
) -> LeakageFinding:
    """Confirm a supervised label that is not the capped time until the end.

    Args:
        rows: ``(prediction_time, episode_end, label)`` for supervised rows.
        rul_cap: Piecewise cap, or None.

    Returns:
        ``CONFIRMED`` when a label is not ``min(end - t, cap)``.
    """
    for prediction_time, episode_end, label in rows:
        expected = episode_end - prediction_time
        if rul_cap is not None:
            expected = min(expected, float(rul_cap))
        if abs(label - expected) > 1e-6:
            return _finding(
                LeakageCheckId.FUTURE_LABELS,
                LeakageStatus.CONFIRMED,
                (
                    "A supervised label is not the capped cycles remaining "
                    f"until the episode end. Expected {expected}, found {label}."
                ),
                "Label remaining life from the episode end and the prediction time only.",
            )
    return _finding(
        LeakageCheckId.FUTURE_LABELS,
        LeakageStatus.PASS,
        "Supervised labels are the capped cycles remaining until the episode end.",
        "Keep the label equal to min(end - t, cap).",
    )


def future_in_features_finding(windows: Sequence[ObservedWindow]) -> LeakageFinding:
    """Confirm a window that contains a row not knowable at ``t``.

    Args:
        windows: Windows the model used.

    Returns:
        ``CONFIRMED`` when a row has event time or available time after ``t``.
    """
    for window in windows:
        for row in window.rows:
            event_time = _time(row, "event_time")
            available_at = _time(row, "available_at")
            if event_time > window.prediction_time or available_at > window.prediction_time:
                return _finding(
                    LeakageCheckId.FUTURE_IN_FEATURES,
                    LeakageStatus.CONFIRMED,
                    (
                        f"A window at {window.prediction_time} contains a row at "
                        f"event_time {event_time} available_at {available_at}."
                    ),
                    "Use only rows with event_time and available_at at or before t.",
                )
    return _finding(
        LeakageCheckId.FUTURE_IN_FEATURES,
        LeakageStatus.PASS,
        "Every window row has event_time and available_at at or before the prediction time.",
        "Keep the causal filter.",
    )


def post_event_features_finding(windows: Sequence[ObservedWindow]) -> LeakageFinding:
    """Confirm a feature row from after the episode end.

    Args:
        windows: Windows the model used.

    Returns:
        ``CONFIRMED`` when a row's event time is after the episode end.
    """
    for window in windows:
        if window.end_time is None:
            continue
        for row in window.rows:
            event_time = _time(row, "event_time")
            if event_time > window.end_time:
                return _finding(
                    LeakageCheckId.POST_EVENT_FEATURES,
                    LeakageStatus.CONFIRMED,
                    (
                        f"A window at {window.prediction_time} uses event_time {event_time}, "
                        f"which is after the episode end {window.end_time}."
                    ),
                    "Do not read rows from after the terminal event.",
                )
    return _finding(
        LeakageCheckId.POST_EVENT_FEATURES,
        LeakageStatus.PASS,
        "No window row is later than its episode end.",
        "Keep post-event rows out of the window.",
    )


def delayed_record_finding(
    *,
    available_at_supplied: bool,
    windows: Sequence[ObservedWindow],
) -> LeakageFinding:
    """Confirm a row used before it was available.

    Args:
        available_at_supplied: True when the signal table has ``available_at``.
        windows: Windows the model used.

    Returns:
        ``NOT_CHECKED`` when the column was not supplied. ``CONFIRMED`` when
        a supplied column is used before its available time.
    """
    if not available_at_supplied:
        return _finding(
            LeakageCheckId.DELAYED_RECORD_LEAK,
            LeakageStatus.NOT_CHECKED,
            "available_at was not supplied, so delayed-record leakage was not checked.",
            "Supply available_at before treating this check as a pass.",
        )
    for window in windows:
        for row in window.rows:
            available_at = _time(row, "available_at")
            if available_at > window.prediction_time:
                return _finding(
                    LeakageCheckId.DELAYED_RECORD_LEAK,
                    LeakageStatus.CONFIRMED,
                    (
                        f"A window at {window.prediction_time} uses a row whose "
                        f"available_at is {available_at}."
                    ),
                    "Wait until available_at before using the row.",
                )
    return _finding(
        LeakageCheckId.DELAYED_RECORD_LEAK,
        LeakageStatus.PASS,
        "No window uses a row before its available_at.",
        "Keep the available_at filter.",
    )


def interpolation_leak_finding(gap_policy: str) -> LeakageFinding:
    """Confirm a gap policy that fills from the future.

    Args:
        gap_policy: Configured gap policy name.

    Returns:
        ``CONFIRMED`` for linear interpolation. ``PASS`` for ``none`` and ``ffill``.
    """
    if gap_policy.casefold() in _INTERPOLATION_POLICIES:
        return _finding(
            LeakageCheckId.INTERPOLATION_LEAK,
            LeakageStatus.CONFIRMED,
            f"Gap policy {gap_policy} fills a time from a later reading.",
            "Use gap_policy none or bounded ffill. Do not interpolate.",
        )
    return _finding(
        LeakageCheckId.INTERPOLATION_LEAK,
        LeakageStatus.PASS,
        f"Gap policy is {gap_policy}. Linear interpolation was not used.",
        "Keep missing values missing, or forward-fill only up to max_gap.",
    )


def entity_leakage_finding(windows: Sequence[ObservedWindow]) -> LeakageFinding:
    """Confirm a window that mixes asset ids.

    Args:
        windows: Windows the model used. Rows may carry ``asset_id``.

    Returns:
        ``CONFIRMED`` when one window contains two asset ids.
    """
    for window in windows:
        identifiers = {
            str(row["asset_id"])
            for row in window.rows
            if "asset_id" in row and str(row["asset_id"]).strip()
        }
        if len(identifiers) > 1:
            listed = ", ".join(sorted(identifiers))
            return _finding(
                LeakageCheckId.ENTITY_LEAKAGE,
                LeakageStatus.CONFIRMED,
                f"One window contains more than one asset: {listed}.",
                "Build each window from a single asset.",
            )
    return _finding(
        LeakageCheckId.ENTITY_LEAKAGE,
        LeakageStatus.PASS,
        "Each window contains rows from one asset.",
        "Keep windows inside one episode.",
    )


def scaler_leakage_finding(
    fit_asset_ids: Sequence[str],
    train_asset_ids: Sequence[str],
) -> LeakageFinding:
    """Confirm a preprocessor fit on an asset outside the training split.

    Args:
        fit_asset_ids: Assets whose rows were used to fit the clip and scaler.
        train_asset_ids: Assets in the training split.

    Returns:
        ``CONFIRMED`` when a fit asset is not a training asset.
    """
    extra = sorted(set(fit_asset_ids) - set(train_asset_ids))
    if extra:
        listed = ", ".join(extra)
        return _finding(
            LeakageCheckId.SCALER_LEAKAGE,
            LeakageStatus.CONFIRMED,
            f"The clip and scaler were fit using assets outside the training split: {listed}.",
            "Fit clip bounds and the scaler on the training split only.",
        )
    return _finding(
        LeakageCheckId.SCALER_LEAKAGE,
        LeakageStatus.PASS,
        "Clip bounds and the scaler were fit on training assets only.",
        "Keep the transformer membership on the training split.",
    )


def target_in_features_finding(
    feature_names: Sequence[str],
    rows: Sequence[tuple[Mapping[str, float | None], float]] | None = None,
) -> LeakageFinding:
    """Confirm a target used as a feature.

    A name matches after separators and capitals are removed, and a lookback
    suffix is stripped first. A feature whose values equal the target on the
    training rows is the same leak when the column was given an innocent name.

    Args:
        feature_names: Names the model received, including lookback suffixes.
        rows: Training ``(features, target)`` pairs. Omit them to check names only.

    Returns:
        ``CONFIRMED`` when a name is a target name or a feature copies the target.
    """
    for name in feature_names:
        if any(column_is_target_name(candidate) for candidate in _name_and_base(name)):
            return _finding(
                LeakageCheckId.TARGET_IN_FEATURES,
                LeakageStatus.CONFIRMED,
                f"Feature {name} is a target column.",
                "Remove the target from the feature allowlist.",
            )
    if rows:
        for name in feature_names:
            if _feature_copies_target(rows, name):
                return _finding(
                    LeakageCheckId.TARGET_IN_FEATURES,
                    LeakageStatus.CONFIRMED,
                    f"Feature {name} equals the training target on every scored row.",
                    "Remove the column that copies remaining life.",
                )
    return _finding(
        LeakageCheckId.TARGET_IN_FEATURES,
        LeakageStatus.PASS,
        "No feature name is a target column, and no feature copies the training target.",
        "Keep remaining life out of the feature allowlist.",
    )


def event_metadata_in_features_finding(
    feature_names: Sequence[str],
    forbidden: Sequence[str],
) -> LeakageFinding:
    """Confirm event metadata used as a feature.

    Args:
        feature_names: Names the model received.
        forbidden: Columns listed in ``forbidden_as_features``.

    Returns:
        ``CONFIRMED`` when a feature matches a forbidden name.
    """
    blocked = {name.casefold() for name in forbidden}
    for name in feature_names:
        if any(candidate.casefold() in blocked for candidate in _name_and_base(name)):
            return _finding(
                LeakageCheckId.EVENT_METADATA_IN_FEATURES,
                LeakageStatus.CONFIRMED,
                f"Feature {name} is event metadata.",
                "Remove event metadata from the feature allowlist.",
            )
    return _finding(
        LeakageCheckId.EVENT_METADATA_IN_FEATURES,
        LeakageStatus.PASS,
        "No feature name is event metadata.",
        "Keep forbidden event columns out of the allowlist.",
    )


def silent_negative_censoring_finding(
    censored_ids: Sequence[str],
    split_ids: Sequence[str],
    labeled_ids: Sequence[str],
) -> LeakageFinding:
    """Confirm a censored asset used as a negative training or split row.

    Args:
        censored_ids: Censored or unsupported assets.
        split_ids: Assets placed in train, validation, or test.
        labeled_ids: Assets that received a supervised label.

    Returns:
        ``CONFIRMED`` when a censored asset is in a split or has a supervised label.
    """
    overlap = sorted(set(censored_ids) & (set(split_ids) | set(labeled_ids)))
    if overlap:
        listed = ", ".join(overlap)
        return _finding(
            LeakageCheckId.SILENT_NEGATIVE_CENSORING,
            LeakageStatus.CONFIRMED,
            f"Censored or unsupported assets were placed in a split or labeled: {listed}.",
            "Report or reject those histories. Do not treat them as negative examples.",
        )
    return _finding(
        LeakageCheckId.SILENT_NEGATIVE_CENSORING,
        LeakageStatus.PASS,
        "Censored and unsupported assets are absent from the splits and from supervised labels.",
        "Keep those histories out of the training loss.",
    )


def unsupported_history_finding(
    censored_ids: Sequence[str],
    reported_ids: Sequence[str],
) -> LeakageFinding:
    """Confirm a censored asset that was omitted from the report.

    Args:
        censored_ids: Censored or unsupported assets present in the data.
        reported_ids: Assets named in the report's censored list.

    Returns:
        ``CONFIRMED`` when a censored asset is missing from that list.
    """
    missing = [asset_id for asset_id in censored_ids if asset_id not in set(reported_ids)]
    if missing:
        listed = ", ".join(missing)
        return _finding(
            LeakageCheckId.UNSUPPORTED_HISTORY,
            LeakageStatus.CONFIRMED,
            f"Censored or unsupported assets were not named in the report: {listed}.",
            "List every censored or unsupported asset. Do not drop it quietly.",
        )
    if censored_ids:
        listed = ", ".join(censored_ids)
        evidence = (
            "Censored or unsupported assets were excluded from training "
            f"and listed in the report: {listed}."
        )
    else:
        evidence = "No censored or unsupported assets were present."
    return _finding(
        LeakageCheckId.UNSUPPORTED_HISTORY,
        LeakageStatus.PASS,
        evidence,
        "Keep reject or report. Do not drop these histories.",
    )


def replacement_episode_mix_finding(
    spans: Mapping[str, tuple[float, float]],
    replacements: Sequence[tuple[str, float]],
) -> LeakageFinding:
    """Confirm a replacement that falls inside one episode's signal span.

    Args:
        spans: Asset id to the first and last signal times of its episode.
        replacements: Asset id and replacement time.

    Returns:
        ``CONFIRMED`` when a replacement time is strictly inside a span.
    """
    for asset_id, replacement_time in replacements:
        span = spans.get(asset_id)
        if span is not None and span[0] < replacement_time < span[1]:
            return _finding(
                LeakageCheckId.REPLACEMENT_EPISODE_MIX,
                LeakageStatus.CONFIRMED,
                (
                    f"Asset {asset_id} has a replacement at {replacement_time} "
                    f"inside the signal span {span[0]} to {span[1]}."
                ),
                "Start a new episode at the replacement. Do not mix the two lives.",
            )
    return _finding(
        LeakageCheckId.REPLACEMENT_EPISODE_MIX,
        LeakageStatus.PASS,
        "No replacement event falls strictly inside an episode.",
        "Split episodes at replacement events.",
    )


def choice_split_finding(
    early_stopping_asset_ids: Sequence[str],
    selection_asset_ids: Sequence[str],
    test_asset_ids: Sequence[str],
) -> LeakageFinding:
    """Confirm a choice that read a test asset.

    Args:
        early_stopping_asset_ids: Assets whose rows were passed to early stopping.
        selection_asset_ids: Assets whose scores chose the headline model.
        test_asset_ids: Assets in the final test split.

    Returns:
        ``CONFIRMED`` when early stopping or model selection saw a test asset.
    """
    test_ids = set(test_asset_ids)
    early_overlap = sorted(set(early_stopping_asset_ids) & test_ids)
    selection_overlap = sorted(set(selection_asset_ids) & test_ids)
    if early_overlap or selection_overlap:
        return _finding(
            LeakageCheckId.TEST_USED_FOR_CHOICES,
            LeakageStatus.CONFIRMED,
            (
                "Early stopping saw test assets "
                f"{early_overlap or 'none'}, and model selection saw test assets "
                f"{selection_overlap or 'none'}."
            ),
            "Choose the iteration count and the headline model on validation only.",
        )
    return _finding(
        LeakageCheckId.TEST_USED_FOR_CHOICES,
        LeakageStatus.PASS,
        (
            f"Early stopping used {len(set(early_stopping_asset_ids))} assets and "
            f"model selection used {len(set(selection_asset_ids))} assets. "
            "None of them are in the test split."
        ),
        "Do not use the test split to choose iterations or the headline model.",
    )


def high_association_finding(
    rows: Sequence[tuple[Mapping[str, float | None], float]],
    *,
    threshold: float,
) -> LeakageFinding:
    """Warn when a training feature tracks the target.

    Association is the absolute Pearson correlation on the training rows
    only. The test split is not an argument. A constant feature is skipped.

    Args:
        rows: Training ``(features, target)`` pairs, before scaling.
        threshold: Absolute correlation that warns. The run does not abort.

    Returns:
        ``WARNING`` at or above the threshold, ``PASS`` when every computed
        correlation is below it, and ``NOT_CHECKED`` when no correlation
        can be computed.
    """
    if len(rows) < 3:
        return _finding(
            LeakageCheckId.HIGH_ASSOCIATION_WITH_LABEL,
            LeakageStatus.NOT_CHECKED,
            "Fewer than three training rows, so association was not computed.",
            "Score association on the training rows once the split has three of them.",
        )
    names = sorted({name for features, _label in rows for name in features})
    scored: list[tuple[float, str]] = []
    for name in names:
        coefficient = _pearson(rows, name)
        if coefficient is None:
            continue
        scored.append((abs(coefficient), name))
    if not scored:
        return _finding(
            LeakageCheckId.HIGH_ASSOCIATION_WITH_LABEL,
            LeakageStatus.NOT_CHECKED,
            "No training feature had enough variation to correlate with the target.",
            "Do not treat a constant column as evidence that the target is absent.",
        )
    scored.sort(reverse=True)
    flagged = [(coefficient, name) for coefficient, name in scored if coefficient >= threshold]
    strongest, strongest_name = scored[0]
    if not flagged:
        return _finding(
            LeakageCheckId.HIGH_ASSOCIATION_WITH_LABEL,
            LeakageStatus.PASS,
            (
                f"The strongest training association is {strongest:.6f} for {strongest_name}, "
                f"below {threshold}."
            ),
            "Keep inspecting features that move with remaining life.",
        )
    listed = ", ".join(f"{name} ({coefficient:.6f})" for coefficient, name in flagged[:12])
    extra = len(flagged) - 12
    if extra > 0:
        listed = f"{listed}, and {extra} more"
    return _finding(
        LeakageCheckId.HIGH_ASSOCIATION_WITH_LABEL,
        LeakageStatus.WARNING,
        (f"{len(flagged)} training features reach absolute correlation {threshold}: {listed}."),
        "Inspect those features. A column that copies the target is a fail_on leak.",
    )


def official_hidden_label_finding(
    *,
    train_asset_ids: Sequence[str],
    official_asset_ids: Sequence[str],
    training_used_official_file: bool,
) -> LeakageFinding:
    """Confirm that official hidden labels were used as training targets.

    Args:
        train_asset_ids: Assets in the training split.
        official_asset_ids: Engines whose truth comes from the official RUL file.
        training_used_official_file: True when a training target was read from that file.

    Returns:
        ``CONFIRMED`` on overlap or when the file was a training target.
    """
    overlap = sorted(set(train_asset_ids) & set(official_asset_ids))
    if training_used_official_file or overlap:
        detail = "The official RUL file was used as a training target."
        if overlap:
            detail = f"Training assets overlap the official test engines: {', '.join(overlap)}."
        return _finding(
            LeakageCheckId.OFFICIAL_HIDDEN_LABEL_RECONSTRUCTION,
            LeakageStatus.CONFIRMED,
            detail,
            "Use the official RUL file only as test truth at the last observation.",
        )
    if official_asset_ids:
        evidence = (
            "The official RUL file is test truth for the last observation. "
            "It is not a training target, and those engines are not in the training split."
        )
    else:
        evidence = "This run has no official hidden-label file."
    return _finding(
        LeakageCheckId.OFFICIAL_HIDDEN_LABEL_RECONSTRUCTION,
        LeakageStatus.PASS,
        evidence,
        "Do not reconstruct official test labels into the training targets.",
    )


def confirmed_fail_on_ids(
    findings: Sequence[LeakageFinding],
    fail_on: Sequence[LeakageCheckId],
) -> tuple[str, ...]:
    """Return the fail-on checks whose status is ``CONFIRMED``.

    Args:
        findings: Audit rows.
        fail_on: Checks that abort the run.

    Returns:
        Check ids, in finding order. A warning-only check is omitted.
    """
    blocked = set(fail_on)
    return tuple(
        finding.check_id.value
        for finding in findings
        if finding.status is LeakageStatus.CONFIRMED and finding.check_id in blocked
    )


def _feature_copies_target(
    rows: Sequence[tuple[Mapping[str, float | None], float]],
    feature_name: str,
) -> bool:
    """Return whether a feature equals the target on every numeric row.

    Args:
        rows: Training feature rows and targets.
        feature_name: Column to compare.

    Returns:
        True when at least two rows are numeric and each feature equals its target.
    """
    pairs: list[tuple[float, float]] = []
    for features, label in rows:
        value = features.get(feature_name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        pairs.append((float(value), float(label)))
    if len(pairs) < 2:
        return False
    return all(_close(value, label) for value, label in pairs)


def _pearson(
    rows: Sequence[tuple[Mapping[str, float | None], float]],
    feature_name: str,
) -> float | None:
    """Return the Pearson correlation of one feature with the target.

    Args:
        rows: Training feature rows and targets.
        feature_name: Column to correlate.

    Returns:
        The correlation, or None when fewer than three pairs vary.
    """
    pairs: list[tuple[float, float]] = []
    for features, label in rows:
        value = features.get(feature_name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not math.isfinite(float(value)) or not math.isfinite(float(label)):
            continue
        pairs.append((float(value), float(label)))
    if len(pairs) < 3:
        return None
    count = float(len(pairs))
    mean_feature = math.fsum(value for value, _label in pairs) / count
    mean_label = math.fsum(label for _value, label in pairs) / count
    feature_square = math.fsum((value - mean_feature) ** 2 for value, _label in pairs)
    label_square = math.fsum((label - mean_label) ** 2 for _value, label in pairs)
    if feature_square <= 0.0 or label_square <= 0.0:
        return None
    covariance = math.fsum((value - mean_feature) * (label - mean_label) for value, label in pairs)
    return covariance / math.sqrt(feature_square * label_square)


def _close(left: float, right: float) -> bool:
    """Return whether two finite numbers agree relative to their size.

    Args:
        left: Feature value.
        right: Target value.

    Returns:
        True when the absolute gap is at most one millionth of the larger magnitude.
    """
    return abs(left - right) <= 1e-6 * max(1.0, abs(left), abs(right))


def _name_and_base(feature_name: str) -> tuple[str, ...]:
    """Return a feature name and its lookback base when it has a suffix.

    Args:
        feature_name: Model feature name.

    Returns:
        The name, plus the base when it ends in ``_mean`` or ``_slope``.
    """
    for suffix in _FEATURE_SUFFIXES:
        if feature_name.endswith(suffix) and len(feature_name) > len(suffix):
            return (feature_name, feature_name[: -len(suffix)])
    return (feature_name,)


def _time(row: Mapping[str, object], key: str) -> float:
    """Read a finite time from a window row.

    Args:
        row: Window row.
        key: ``event_time`` or ``available_at``.

    Returns:
        The time.

    Raises:
        ConfigurationError: The field is missing or not numeric.
    """
    if key not in row:
        raise ConfigurationError(f"Window row is missing {key}.")
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float, str)) or value == "":
        raise ConfigurationError(f"Window row has a non-numeric {key}.")
    try:
        return float(value)
    except ValueError as error:
        raise ConfigurationError(f"Window row has a non-numeric {key}.") from error


def _finding(
    check_id: LeakageCheckId, status: LeakageStatus, evidence: str, remedy: str
) -> LeakageFinding:
    """Build one audit row.

    Args:
        check_id: Check that produced the row.
        status: Confirmed, not checked, or pass.
        evidence: What was observed.
        remedy: What to change.

    Returns:
        The finding.
    """
    return LeakageFinding(check_id=check_id, status=status, evidence=evidence, remedy=remedy)
