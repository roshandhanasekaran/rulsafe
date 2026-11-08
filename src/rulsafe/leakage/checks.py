"""One leakage finding and a reserved generic check interface.

The v0.1 pipeline runs its implemented checks from ``rulsafe.leakage.fail_on``.
``AuditContext`` and ``run_check`` are internal placeholders for a future
generic registry and are not called by the public pipeline. A finding that is
never written is not a pass;
:func:`rulsafe.leakage.report.with_documented_coverage` turns a missing check
into ``NOT_CHECKED``.
"""

from dataclasses import dataclass

from rulsafe.config import LeakageCheckId, LeakageStatus
from rulsafe.exceptions import not_implemented


@dataclass(frozen=True)
class LeakageFinding:
    """One row of the leakage audit.

    Attributes:
        check_id: Which check produced the row.
        status: Confirmed, warning, not checked, or pass.
        evidence: What was observed. Empty evidence is rejected.
        remedy: What a person should change. Empty remedy is rejected.
    """

    check_id: LeakageCheckId
    status: LeakageStatus
    evidence: str
    remedy: str

    def __post_init__(self) -> None:
        """Reject a finding that does not say what happened or what to do."""
        if not self.evidence.strip():
            raise ValueError("Leakage evidence must not be empty.")
        if not self.remedy.strip():
            raise ValueError("Leakage remedy must not be empty.")


class AuditContext:
    """Inputs reserved for a future generic leakage-check registry.

    Attributes:
        protocol_name: Split protocol used for the run.
        censored_policy: Whether unsupported histories are rejected or reported.
    """

    def __init__(self, protocol_name: str, censored_policy: str) -> None:
        """Store the fields a check is allowed to read.

        Args:
            protocol_name: ``official_partitions`` or ``group_holdout``.
            censored_policy: ``reject`` or ``report``.
        """
        self.protocol_name = protocol_name
        self.censored_policy = censored_policy


def run_check(check_id: LeakageCheckId, context: AuditContext) -> LeakageFinding:
    """Reserved entry point for a future generic leakage-check registry.

    Args:
        check_id: Check to run.
        context: Protocol and censoring policy for the run.

    Returns:
        The finding, with evidence and a remedy.

    Raises:
        NotImplementedError: This reserved registry is not implemented.
    """
    raise not_implemented("run_check", check_id, context)
