"""Rich terminal summary.

The summary shows cohort counts, the leakage table, the validation
leaderboard, history dispositions, and the path of the HTML file.
"""

from collections.abc import Mapping

from rulsafe.exceptions import not_implemented


def render_terminal_summary(report_document: Mapping[str, object]) -> str:
    """Render the terminal summary.

    Args:
        report_document: Report fields shared with HTML and JSON.

    Returns:
        Text that a Rich console can print.

    Raises:
        NotImplementedError: The terminal summary is not implemented yet.
    """
    raise not_implemented("render_terminal_summary", report_document)
