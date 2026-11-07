"""Leakage audit.

Statuses are ``CONFIRMED``, ``WARNING``, ``NOT_CHECKED``, and ``PASS``.
Missing checks are filled in as ``NOT_CHECKED`` so the report shows its coverage.
"""

from rulsafe.leakage.checks import LeakageFinding as LeakageFinding
from rulsafe.leakage.report import with_documented_coverage as with_documented_coverage
from rulsafe.leakage.suite import LeakageSuiteResult as LeakageSuiteResult
from rulsafe.leakage.suite import worst_leakage_status as worst_leakage_status

__all__ = [
    "LeakageFinding",
    "LeakageSuiteResult",
    "with_documented_coverage",
    "worst_leakage_status",
]
