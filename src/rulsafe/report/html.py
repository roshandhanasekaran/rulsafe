"""Self-contained HTML report.

The file inlines its CSS and embeds plot images. It does not start a web
server. The banner must say this is research software, not a certified
prognostic, and that the audit is not a guarantee.
"""

from collections.abc import Mapping
from pathlib import Path

from rulsafe.exceptions import not_implemented


def write_html_report(report_document: Mapping[str, object], path: Path) -> Path:
    """Write the self-contained HTML report.

    Args:
        report_document: Same structure as the JSON report, including coverage.
        path: Destination path.

    Returns:
        The path that was written.

    Raises:
        NotImplementedError: HTML rendering is not implemented yet.
    """
    raise not_implemented("write_html_report", report_document, path)
