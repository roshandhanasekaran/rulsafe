"""Leakage result helpers and a reserved generic suite entry point.

An empty finding list is ``NOT_CHECKED``, not ``PASS``. Confirmed is more
serious than warning, warning is more serious than not checked, and not
checked is more serious than pass. The v0.1 public pipeline assembles its
implemented findings directly; ``run_leakage_suite`` is an internal placeholder
that it does not call.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from rulsafe.config import LeakageStatus
from rulsafe.exceptions import not_implemented
from rulsafe.leakage.checks import AuditContext, LeakageFinding

_STATUS_SEVERITY: dict[LeakageStatus, int] = {
    LeakageStatus.PASS: 0,
    LeakageStatus.NOT_CHECKED: 1,
    LeakageStatus.WARNING: 2,
    LeakageStatus.CONFIRMED: 3,
}


def worst_leakage_status(findings: Sequence[LeakageFinding]) -> LeakageStatus:
    """Return the most serious status in a finding list.

    Args:
        findings: Audit rows. An empty sequence was not checked.

    Returns:
        ``NOT_CHECKED`` when nothing was recorded, otherwise the worst status.
    """
    if not findings:
        return LeakageStatus.NOT_CHECKED
    worst = findings[0]
    for finding in findings[1:]:
        if _STATUS_SEVERITY[finding.status] > _STATUS_SEVERITY[worst.status]:
            worst = finding
    return worst.status


@dataclass(frozen=True)
class LeakageSuiteResult:
    """Findings produced by the leakage suite.

    Attributes:
        findings: Rows in the audit. Coverage is documented separately.
    """

    findings: tuple[LeakageFinding, ...]

    @property
    def worst_status(self) -> LeakageStatus:
        """Return the most serious status among the findings.

        Returns:
            The worst status, or ``NOT_CHECKED`` when there are no findings.
        """
        return worst_leakage_status(self.findings)


def run_leakage_suite(context: AuditContext) -> LeakageSuiteResult:
    """Reserved entry point for a future generic leakage suite.

    A confirmed ``fail_on`` check aborts training after the report is written.
    The report must not say the audit found no leakage in general.

    Args:
        context: Protocol and censoring policy.

    Returns:
        Findings, including ``NOT_CHECKED`` for checks that did not run.

    Raises:
        NotImplementedError: This reserved suite entry point is not implemented.
    """
    raise not_implemented("run_leakage_suite", context)
