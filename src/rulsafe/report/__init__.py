"""Report writers.

HTML and JSON are required. The terminal summary is a compact plain-text view
of the same document. Sections that v0.1 does not compute stay explicit.
"""

from rulsafe.report.html import write_html_report as write_html_report
from rulsafe.report.json import MetricComputationStatus as MetricComputationStatus
from rulsafe.report.json import MetricValue as MetricValue
from rulsafe.report.json import write_json_report as write_json_report
from rulsafe.report.terminal import render_terminal_summary as render_terminal_summary

__all__ = [
    "MetricComputationStatus",
    "MetricValue",
    "render_terminal_summary",
    "write_html_report",
    "write_json_report",
]
