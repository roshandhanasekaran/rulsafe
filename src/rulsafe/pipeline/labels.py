"""Targets for completed trajectories, and the fate of every other history.

v0.1 scores remaining useful life when a trajectory is completed, and scores
the official last observation for C-MAPSS test engines. A censored or
unsupported history is rejected or reported. It is never dropped without a
finding.
"""

from enum import Enum

from rulsafe.config import CensoredHistoryPolicy
from rulsafe.exceptions import not_implemented


class HistorySupport(str, Enum):
    """Whether v0.1 knows how to score a history."""

    COMPLETED = "completed"
    OFFICIAL_LAST_OBSERVATION = "official_last_observation"
    CENSORED = "censored"
    UNSUPPORTED = "unsupported"


class HistoryDisposition(str, Enum):
    """What the run does with a history. There is no silent-drop value."""

    TRAIN = "train"
    SCORE_LAST_OBSERVATION = "score_last_observation"
    REJECT = "reject"
    REPORT = "report"


def disposition_for_history(
    support: HistorySupport,
    policy: CensoredHistoryPolicy,
) -> HistoryDisposition:
    """Choose an explicit disposition for one history.

    Completed trajectories are trainable. Official C-MAPSS test endings are
    scored at the last observation. Every other history follows
    ``censored_policy``: ``reject`` aborts the run and ``report`` keeps an
    audit row. Neither path removes the history quietly.

    Args:
        support: What kind of history this is.
        policy: Configured policy for censored and unsupported histories.

    Returns:
        The disposition that later stages must honor.
    """
    if support is HistorySupport.COMPLETED:
        return HistoryDisposition.TRAIN
    if support is HistorySupport.OFFICIAL_LAST_OBSERVATION:
        return HistoryDisposition.SCORE_LAST_OBSERVATION
    if policy is CensoredHistoryPolicy.REJECT:
        return HistoryDisposition.REJECT
    return HistoryDisposition.REPORT


def assign_remaining_life(
    *,
    support: HistorySupport,
    policy: CensoredHistoryPolicy,
) -> float | None:
    """Assign a remaining-life target, or refuse a history v0.1 cannot score.

    Args:
        support: What kind of history this is.
        policy: Configured policy for censored and unsupported histories.

    Returns:
        Remaining life for a trainable or last-observation history.

    Raises:
        NotImplementedError: Target assignment is not implemented yet.
    """
    raise not_implemented("assign_remaining_life", support, policy)
