"""Plain-text terminal summary.

The summary shows the run status, headline metrics, leakage findings, excluded
history dispositions, and the path of the HTML file. Dynamic text is reduced
to printable single-line content before it is returned to a terminal.
"""

from collections.abc import Mapping, Sequence


def render_terminal_summary(report_document: Mapping[str, object]) -> str:
    """Render the terminal summary.

    Args:
        report_document: Report fields shared with HTML and JSON.

    Returns:
        Printable plain text ending in one newline.
    """
    title = _text(report_document.get("title"), _text(report_document.get("project"), "RULSafe"))
    lines = [title, f"Status: {_text(report_document.get('status'), 'UNKNOWN')}"]
    for label, key in (
        ("Project", "project"),
        ("Assets", "asset_count"),
        ("Headline model", "headline_model"),
        ("Headline split", "headline_split"),
    ):
        value = report_document.get(key)
        if value is not None:
            lines.append(f"{label}: {_text(value, 'unknown')}")
    _append_headline_metrics(lines, report_document.get("headline_metrics"))
    _append_leakage(lines, report_document.get("leakage"))
    _append_histories(lines, report_document.get("history_dispositions"))
    report_html = report_document.get("report_html")
    if report_html is not None:
        lines.append(f"HTML report: {_text(report_html, 'unknown')}")
    return "\n".join(lines) + "\n"


def _append_headline_metrics(lines: list[str], metrics: object) -> None:
    """Append metric values and computation statuses when present."""
    if not isinstance(metrics, Mapping):
        return
    rows: list[str] = []
    for name, payload in metrics.items():
        if not isinstance(payload, Mapping) or "value" not in payload:
            continue
        value = _text(payload.get("value"), "null")
        status = _text(payload.get("status"), "UNKNOWN")
        rows.append(f"  {_text(name, 'metric')}: {value} ({status})")
    if rows:
        lines.append("Headline metrics:")
        lines.extend(rows)


def _append_leakage(lines: list[str], leakage: object) -> None:
    """Append each recorded leakage finding."""
    if not isinstance(leakage, Sequence) or isinstance(leakage, str):
        return
    rows: list[str] = []
    for finding in leakage:
        if not isinstance(finding, Mapping):
            continue
        check_id = _text(finding.get("check_id"), "unknown_check")
        status = _text(finding.get("status"), "UNKNOWN")
        evidence = _text(finding.get("evidence"), "No evidence recorded.")
        rows.append(f"  [{status}] {check_id}: {evidence}")
    if rows:
        lines.append("Leakage findings:")
        lines.extend(rows)


def _append_histories(lines: list[str], histories: object) -> None:
    """Append histories that the report excluded from fitting and scoring."""
    if not isinstance(histories, Sequence) or isinstance(histories, str):
        return
    rows: list[str] = []
    for history in histories:
        if not isinstance(history, Mapping):
            continue
        asset_id = _text(history.get("asset_id"), "unknown_asset")
        support = _text(history.get("support"), "unknown")
        disposition = _text(history.get("disposition"), "unknown")
        rows.append(f"  {asset_id}: {support} / {disposition}")
    if rows:
        lines.append("Excluded histories:")
        lines.extend(rows)


def _text(value: object, default: str) -> str:
    """Return printable single-line text, or a default for an empty value."""
    candidate = value if isinstance(value, str) else str(value) if value is not None else ""
    cleaned = "".join(character if character.isprintable() else " " for character in candidate)
    return cleaned.strip() or default
