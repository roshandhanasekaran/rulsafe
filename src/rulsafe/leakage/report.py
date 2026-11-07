"""Text form of a leakage finding, and explicit coverage for missing checks."""

from collections.abc import Sequence

from rulsafe.config import LeakageCheckId, LeakageStatus
from rulsafe.leakage.checks import LeakageFinding


def format_finding(finding: LeakageFinding) -> str:
    """Format one finding as plain text.

    Args:
        finding: Audit row to render.

    Returns:
        The four-line block used in the terminal and in fixtures.
    """
    return (
        f"check_id: {finding.check_id.value}\n"
        f"status: {finding.status.value}\n"
        f'evidence: "{finding.evidence}"\n'
        f'remedy: "{finding.remedy}"\n'
    )


def with_documented_coverage(findings: Sequence[LeakageFinding]) -> tuple[LeakageFinding, ...]:
    """Add ``NOT_CHECKED`` for every known check that has no finding.

    Recorded findings are kept in check-identifier order. A missing check is
    not treated as a pass and is not omitted.

    Args:
        findings: Findings the suite actually produced.

    Returns:
        One or more findings for every :class:`LeakageCheckId`.
    """
    recorded: dict[LeakageCheckId, list[LeakageFinding]] = {}
    for finding in findings:
        recorded.setdefault(finding.check_id, []).append(finding)
    documented: list[LeakageFinding] = []
    for check_id in LeakageCheckId:
        existing = recorded.get(check_id)
        if existing:
            documented.extend(existing)
            continue
        documented.append(
            LeakageFinding(
                check_id=check_id,
                status=LeakageStatus.NOT_CHECKED,
                evidence="No result was recorded for this check.",
                remedy=(
                    "Do not treat a missing check as a pass. "
                    "Record PASS, CONFIRMED, WARNING, or NOT_CHECKED."
                ),
            )
        )
    return tuple(documented)
