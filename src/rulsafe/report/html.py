"""Self-contained HTML report.

The file inlines its CSS. It does not start a web server and does not load
a remote stylesheet or script. The banner says this is research software,
not a certified prognostic, and that a pass is not a guarantee.
"""

import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

_STYLE = """
body { margin: 0; font-family: "Iowan Old Style", Palatino, Georgia, serif;
  color: #1c1915; background: #f6f3ec; }
main { max-width: 920px; margin: 0 auto; padding: 32px 20px 64px; }
h1 { font-size: 2rem; line-height: 1.15; margin: 0 0 8px; }
h2 { font-size: 1.25rem; margin: 32px 0 8px; }
p, li { line-height: 1.45; }
.banner { background: #2d241c; color: #f6f3ec; padding: 16px 18px; border-radius: 8px; }
.banner p { margin: 0; }
.meta { display: grid; grid-template-columns: 160px 1fr; gap: 6px 12px; margin-top: 18px; }
.meta dt { color: #5c5348; }
.meta dd { margin: 0; }
table { width: 100%; border-collapse: collapse; background: white; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e4ddd0;
  vertical-align: top; }
th { font-size: 0.85rem; letter-spacing: 0.02em; color: #5c5348; }
.wrap { overflow-x: auto; }
.status-FAILED, .status-CONFIRMED { color: #8c2f2f; font-weight: 700; }
.status-PASS { color: #1f6b45; }
.status-NOT_CHECKED, .status-WARNING { color: #8a5a12; }
footer { margin-top: 36px; color: #5c5348; font-size: 0.95rem; }
"""


def render_html(report_document: Mapping[str, object]) -> str:
    """Render the report document as a self-contained HTML page.

    Args:
        report_document: Same structure as the JSON report.

    Returns:
        An HTML document. Dynamic text is escaped.
    """
    project = _text(report_document.get("project"), "RULSafe")
    title = _text(report_document.get("title"), project)
    status = _text(report_document.get("status"), "UNKNOWN")
    split_order = _report_split_order(report_document)
    disclaimer = _text(
        report_document.get("disclaimer"),
        "Research software, not a safety-certified prognostic. "
        "A listed pass is not a guarantee that every leak was checked.",
    )
    metadata = [
        ("Project", project),
        ("Status", status),
        ("Headline model", _text(report_document.get("headline_model"), "none")),
        ("Headline split", _text(report_document.get("headline_split"), "none")),
        ("RUL cap", _cap_text(report_document.get("rul_cap"))),
        ("Selection split", _text(report_document.get("selection_split"), "none")),
    ]
    optional_metadata = (
        ("Project notes", report_document.get("project_notes")),
        ("Label unit", report_document.get("label_unit")),
        ("Timestamp type", report_document.get("timestamp_type")),
    )
    metadata.extend(
        (label, value) for label, raw_value in optional_metadata if (value := _text(raw_value, ""))
    )
    metadata.append(("Report split order", ", ".join(split_order)))
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(title)}</title>",
        f"<style>{_STYLE}</style>",
        "</head>",
        "<body>",
        "<main>",
        f"<h1>{html.escape(title)}</h1>",
        f'<div class="banner"><p>{html.escape(disclaimer)}</p></div>',
        _definition_list(metadata),
        _protocol_section(report_document),
        _split_metrics_section(report_document.get("metrics"), split_order),
        _metrics_section("Headline metrics", report_document.get("headline_metrics")),
        _intervals_section(report_document.get("confidence_intervals")),
        _official_section(report_document.get("official_benchmark"), split_order),
        _secondary_section(report_document.get("secondary_evaluation"), split_order),
        _preprocessing_section(report_document),
        _leakage_section(report_document.get("leakage")),
        _violations_section(report_document.get("contract_violations")),
        f"<footer><p>{html.escape(disclaimer)}</p></footer>",
        "</main>",
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)


def write_html_report(report_document: Mapping[str, object], path: Path) -> Path:
    """Write the self-contained HTML report.

    Args:
        report_document: Same structure as the JSON report, including coverage.
        path: Destination path.

    Returns:
        The path that was written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report_document), encoding="utf-8")
    return path


def _protocol_section(document: Mapping[str, object]) -> str:
    """Render the evaluation protocol paragraph.

    Args:
        document: Report body.

    Returns:
        An HTML section, or an empty string when the protocol is absent.
    """
    protocol = document.get("evaluation_protocol")
    if not isinstance(protocol, Mapping):
        return ""
    description = _text(protocol.get("description"), "")
    name = _text(protocol.get("name"), "")
    nasa = _text(protocol.get("nasa_score"), "")
    return (
        "<h2>Evaluation protocol</h2>"
        f"<p><strong>{html.escape(name)}</strong></p>"
        f"<p>{html.escape(description)}</p>"
        f"<p>{html.escape(nasa)}</p>"
    )


def _metrics_section(heading: str, metrics: object) -> str:
    """Render a small metric mapping.

    Args:
        heading: Section heading.
        metrics: Metric mapping, or anything else.

    Returns:
        An HTML section, or an empty string.
    """
    if not isinstance(metrics, Mapping):
        return ""
    rows = [(str(key), _display(value)) for key, value in metrics.items()]
    return f"<h2>{html.escape(heading)}</h2>" + _table(("Field", "Value"), rows)


def _intervals_section(intervals: object) -> str:
    """Render bootstrap intervals for the headline and secondary tests.

    Args:
        intervals: The ``confidence_intervals`` object.

    Returns:
        An HTML section, or an empty string.
    """
    if not isinstance(intervals, Mapping):
        return ""
    method = _text(intervals.get("method"), "")
    samples = _display(intervals.get("samples"))
    level = _display(intervals.get("level"))
    seed = _display(intervals.get("seed"))
    intro = (
        "<h2>Bootstrap confidence intervals</h2>"
        f"<p>{html.escape(method)}. Samples {html.escape(samples)}, "
        f"level {html.escape(level)}, seed {html.escape(seed)}. "
        "Engines are resampled with replacement. The interval is for test "
        "root-mean-square error and mean absolute error.</p>"
    )
    blocks = [intro]
    for key, title in (
        ("headline_test", "Headline test"),
        ("secondary_test", "Secondary test"),
    ):
        block = intervals.get(key)
        if not isinstance(block, Mapping):
            continue
        models = block.get("models")
        if not isinstance(models, Mapping):
            continue
        rows: list[tuple[str, str]] = []
        for model_name, payload in models.items():
            if not isinstance(payload, Mapping):
                continue
            for metric_name in ("root_mean_square_error", "mean_absolute_error"):
                metric = payload.get(metric_name)
                if isinstance(metric, Mapping):
                    rows.append((f"{model_name} {metric_name}", _interval_text(metric)))
        if rows:
            blocks.append(f"<h3>{html.escape(title)}</h3>" + _table(("Metric", "Interval"), rows))
    return "".join(blocks)


def _official_section(official: object, split_order: Sequence[str]) -> str:
    """Render the official FD001 benchmark block.

    Args:
        official: The ``official_benchmark`` object, or None.
        split_order: Configured order for any split blocks that are present.

    Returns:
        An HTML section, or an empty string.
    """
    if not isinstance(official, Mapping):
        return ""
    parts = [
        "<h2>Official FD001 benchmark</h2>",
        f"<p>{html.escape(_text(official.get('truth'), ''))}</p>",
        f"<p>{html.escape(_text(official.get('validation_source'), ''))}</p>",
        f"<p>{html.escape(_text(official.get('early_stopping'), ''))}</p>",
        f"<p>RUL cap: {html.escape(_cap_text(official.get('rul_cap')))}.</p>",
    ]
    headings = {"validation": "Official-protocol validation", "test": "Official test"}
    for key in split_order:
        heading = headings.get(key)
        if heading is None:
            continue
        block = official.get(key)
        if isinstance(block, Mapping):
            parts.append(_metrics_section(heading, block.get("metrics")))
    return "".join(parts)


def _secondary_section(secondary: object, split_order: Sequence[str]) -> str:
    """Render the per-row secondary view.

    Args:
        secondary: The ``secondary_evaluation`` object, or None.
        split_order: Configured order for any split blocks that are present.

    Returns:
        An HTML section, or an empty string.
    """
    if not isinstance(secondary, Mapping):
        return ""
    parts = [
        "<h2>Secondary evaluation</h2>",
        f"<p>{html.escape(_text(secondary.get('description'), ''))}</p>",
    ]
    metrics = secondary.get("metrics")
    if isinstance(metrics, Mapping):
        for key in split_order:
            if key in metrics:
                parts.append(_metrics_section(f"Secondary {key}", metrics.get(key)))
    return "".join(parts)


def _split_metrics_section(metrics: object, split_order: Sequence[str]) -> str:
    """Render the main split metrics in the configured report order.

    Args:
        metrics: Mapping of split name to its metric block.
        split_order: Configured order for any split blocks that are present.

    Returns:
        HTML sections for each available split.
    """
    if not isinstance(metrics, Mapping):
        return ""
    return "".join(
        _metrics_section(f"{split_name.title()} split metrics", metrics.get(split_name))
        for split_name in split_order
        if split_name in metrics
    )


def _report_split_order(document: Mapping[str, object]) -> tuple[str, ...]:
    """Read a valid report split order, with the schema default as fallback.

    Args:
        document: Report body.

    Returns:
        Train, validation, and test in the configured order.
    """
    default = ("train", "validation", "test")
    raw_order = document.get("report_split_order")
    if not isinstance(raw_order, Sequence) or isinstance(raw_order, str):
        return default
    order = tuple(item for item in raw_order if isinstance(item, str) and item in default)
    if len(order) != len(default) or set(order) != set(default):
        return default
    return order


def _preprocessing_section(document: Mapping[str, object]) -> str:
    """Render the preprocessing and window settings that were applied.

    Args:
        document: Report body.

    Returns:
        An HTML section, or an empty string when neither block is present.
    """
    preprocessing = document.get("preprocessing")
    windows = document.get("windows")
    if not isinstance(preprocessing, Mapping) and not isinstance(windows, Mapping):
        return ""
    rows: list[tuple[str, str]] = []
    if isinstance(preprocessing, Mapping):
        rows.extend(
            (f"preprocessing.{key}", _display(value)) for key, value in preprocessing.items()
        )
    if isinstance(windows, Mapping):
        rows.extend((f"windows.{key}", _display(value)) for key, value in windows.items())
    return "<h2>Preprocessing and windows</h2>" + _table(("Setting", "Value"), rows)


def _leakage_section(leakage: object) -> str:
    """Render the leakage audit.

    Args:
        leakage: Finding list.

    Returns:
        An HTML section, or an empty string.
    """
    if not isinstance(leakage, Sequence) or isinstance(leakage, str):
        return ""
    rows: list[tuple[str, str, str]] = []
    for item in leakage:
        if not isinstance(item, Mapping):
            continue
        status = _text(item.get("status"), "")
        rows.append(
            (
                _text(item.get("check_id"), ""),
                status,
                _text(item.get("evidence"), ""),
            )
        )
    body = "".join(
        "<tr>"
        f"<td>{html.escape(check_id)}</td>"
        f'<td class="status-{html.escape(status)}">{html.escape(status)}</td>'
        f"<td>{html.escape(evidence)}</td>"
        "</tr>"
        for check_id, status, evidence in rows
    )
    return (
        "<h2>Leakage audit</h2>"
        '<div class="wrap"><table><thead><tr>'
        "<th>Check</th><th>Status</th><th>Evidence</th>"
        f"</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _violations_section(violations: object) -> str:
    """Render contract violations when the run stopped early.

    Args:
        violations: Violation list.

    Returns:
        An HTML section, or an empty string.
    """
    if not isinstance(violations, Sequence) or isinstance(violations, str) or not violations:
        return ""
    rows = []
    for item in violations:
        if isinstance(item, Mapping):
            rows.append((_text(item.get("asset_id"), ""), _text(item.get("message"), "")))
    if not rows:
        return ""
    return "<h2>Contract violations</h2>" + _table(("Asset", "Detail"), rows)


def _definition_list(pairs: Sequence[tuple[str, str]]) -> str:
    """Render a definition list.

    Args:
        pairs: Label and value.

    Returns:
        HTML.
    """
    body = "".join(
        f"<dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd>" for label, value in pairs
    )
    return f'<dl class="meta">{body}</dl>'


def _table(headers: tuple[str, str], rows: Sequence[tuple[str, str]]) -> str:
    """Render a two-column table.

    Args:
        headers: Column titles.
        rows: Body rows.

    Returns:
        HTML.
    """
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = "".join(
        f"<tr><td>{html.escape(left)}</td><td>{html.escape(right)}</td></tr>"
        for left, right in rows
    )
    return (
        '<div class="wrap"><table><thead><tr>'
        f"{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _interval_text(metric: Mapping[str, object]) -> str:
    """Format one point and its interval.

    Args:
        metric: Mapping with point, lower, and upper.

    Returns:
        A short text form.
    """
    return (
        f"{_display(metric.get('point'))} "
        f"[{_display(metric.get('lower'))}, {_display(metric.get('upper'))}]"
    )


def _cap_text(value: object) -> str:
    """Format the RUL cap, including an explicit none.

    Args:
        value: Cap integer, None, or another object.

    Returns:
        ``none`` or the number.
    """
    if value is None:
        return "none"
    return _display(value)


def _display(value: object) -> str:
    """Format a report value for HTML.

    Args:
        value: JSON-like value.

    Returns:
        A compact string. Numbers use the JSON encoding.
    """
    if isinstance(value, float):
        return json.dumps(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return "null"
    return str(value)


def _text(value: object, default: str) -> str:
    """Return a string value, or the default.

    Args:
        value: Candidate text.
        default: Used when the value is not a string.

    Returns:
        The text.
    """
    if isinstance(value, str) and value.strip():
        return value
    return default
