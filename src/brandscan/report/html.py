"""The executive summary as a browsable page.

The same model the Markdown renders, rendered for someone who is going to read
the tables rather than diff them. The page is one file with nothing fetched:
the report tree gets copied to a share, and a summary that loses its stylesheet
in transit renders as unstyled soup.
"""

from __future__ import annotations

import re
from html import escape

from brandscan.config.model import Severity
from brandscan.report.summary_model import (
    BAND_PREAMBLE,
    MAX_VALUES_RENDERED,
    MatchRow,
    SummaryModel,
    display_value,
)

_SLUG = re.compile(r"[^a-z0-9]+")

STYLE = """
:root {
  --bg: #ffffff; --fg: #1b1b1f; --muted: #5b5b66; --line: #d9d9e0;
  --head: #f4f4f7; --accent: #24405f;
  --high: #a3242c; --high-bg: #fbe7e8;
  --medium: #8a5a00; --medium-bg: #fbf1dd;
  --low: #2f6136; --low-bg: #e6f3e8;
  --neutral: #444; --neutral-bg: #eeeef2;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #16161a; --fg: #e8e8ec; --muted: #a0a0ad; --line: #35353f;
    --head: #22222a; --accent: #9dc0e6;
    --high: #ff9ba1; --high-bg: #3a1f22;
    --medium: #f0c273; --medium-bg: #372c14;
    --low: #92d49c; --low-bg: #1c3220;
    --neutral: #c8c8d2; --neutral-bg: #2a2a33;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1.5rem 4rem; background: var(--bg); color: var(--fg);
  font: 16px/1.55 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
main { max-width: 68rem; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
h2 { font-size: 1.2rem; margin: 2.5rem 0 .5rem; padding-bottom: .3rem;
     border-bottom: 2px solid var(--line); }
h3 { font-size: 1rem; margin: 1.75rem 0 .5rem; color: var(--accent); }
p { margin: .5rem 0; }
.meta, .note { color: var(--muted); font-size: .9rem; }
.warn { border-left: 4px solid var(--high); background: var(--high-bg);
        color: var(--fg); padding: .75rem 1rem; margin: 1rem 0; }
.wrap { overflow-x: auto; margin: .75rem 0; }
table { border-collapse: collapse; width: 100%; font-size: .92rem; }
caption { text-align: left; color: var(--muted); font-size: .85rem;
          padding-bottom: .4rem; }
th, td { border: 1px solid var(--line); padding: .4rem .6rem; text-align: left;
         vertical-align: top; }
thead th { position: sticky; top: 0; background: var(--head); z-index: 1; }
tbody tr:nth-child(even) { background: color-mix(in srgb, var(--head) 55%, transparent); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
code, .mono { font-family: ui-monospace, Consolas, "Courier New", monospace;
              font-size: .88em; word-break: break-word; }
a { color: var(--accent); }
.pill { display: inline-block; padding: .05rem .5rem; border-radius: 999px;
        font-size: .82rem; font-weight: 600; white-space: nowrap;
        border: 1px solid currentColor;
        color: var(--neutral); background: var(--neutral-bg); }
.pill.sev-high, .pill.band-very-high { color: var(--high); background: var(--high-bg); }
.pill.sev-medium, .pill.band-high { color: var(--medium); background: var(--medium-bg); }
.pill.sev-low, .pill.band-medium { color: var(--low); background: var(--low-bg); }
.sortable thead th { cursor: pointer; }
.sortable thead th::after { content: " \\2195"; color: var(--muted); font-weight: 400; }
.more { color: var(--muted); font-style: italic; }
"""

# Sorting is an enhancement: every row and number is in the markup already, so
# the page is complete and correct with scripting switched off.
SCRIPT = """
document.querySelectorAll('table.sortable').forEach(function (table) {
  var head = table.tHead && table.tHead.rows[0];
  if (!head) return;
  Array.prototype.forEach.call(head.cells, function (cell, index) {
    var ascending = true;
    cell.addEventListener('click', function () {
      var body = table.tBodies[0];
      var rows = Array.prototype.slice.call(body.rows);
      rows.sort(function (a, b) {
        var x = a.cells[index].textContent.trim();
        var y = b.cells[index].textContent.trim();
        var nx = parseFloat(x.replace(/[^0-9.-]/g, ''));
        var ny = parseFloat(y.replace(/[^0-9.-]/g, ''));
        var both = !isNaN(nx) && !isNaN(ny) && x !== '' && y !== '';
        var order = both ? (nx - ny) : x.localeCompare(y);
        return ascending ? order : -order;
      });
      ascending = !ascending;
      rows.forEach(function (row) { body.appendChild(row); });
    });
  });
});
"""


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-") or "none"


def _severity_pill(label: str) -> str:
    """A pill that names itself, so colour is never the only signal."""
    return f'<span class="pill sev-{_slug(label)}">{escape(label)}</span>'


def _band_pill(name: str) -> str:
    return f'<span class="pill band-{_slug(name)}">{escape(name)}</span>'


def _code(text: str) -> str:
    return f"<code>{escape(text)}</code>"


def _link(path: str) -> str:
    if not path:
        return "—"
    return f'<a href="{escape(path, quote=True)}">report</a>'


def _table(caption: str, headers: list[tuple[str, bool]], rows: list[str]) -> list[str]:
    """One table. `headers` pairs a label with whether its column is numeric."""
    head = "".join(
        f'<th class="num" scope="col">{escape(label)}</th>'
        if numeric
        else f'<th scope="col">{escape(label)}</th>'
        for label, numeric in headers
    )
    return [
        '<div class="wrap">',
        '<table class="sortable">',
        f"<caption>{escape(caption)}</caption>",
        f"<thead><tr>{head}</tr></thead>",
        "<tbody>",
        *rows,
        "</tbody>",
        "</table>",
        "</div>",
    ]


def render_summary_html(model: SummaryModel) -> str:
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Brand asset discovery — executive summary</title>",
        f"<style>{STYLE}</style>",
        "</head>",
        "<body>",
        "<main>",
        "<h1>Brand asset discovery — executive summary</h1>",
        f'<p class="meta">Generated {escape(model.generated_at)}</p>',
    ]
    parts += _totals_section(model)
    parts += _errors_section(model)
    parts += _ranking_section(model)
    parts += _breakdown_section(model)
    parts += _values_section(model)
    parts += _bands_section(model)
    parts += _severity_section(model)
    parts += _not_scanned_section(model)
    parts += [
        "</main>",
        f"<script>{SCRIPT}</script>",
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)


def _totals_section(model: SummaryModel) -> list[str]:
    counts = model.totals
    labels = [
        ("Targeted", "targeted"),
        ("Scanned", "scanned"),
        ("Clean (scanned, nothing found)", "clean"),
        ("With findings", "with_findings"),
        ("Skipped (not scanned)", "skipped"),
        ("Failed (not scanned)", "failed"),
    ]
    rows = [
        f"<tr><td>{escape(label)}</td>"
        f'<td class="num">{counts[key]}</td></tr>'
        for label, key in labels
    ]
    parts = ["<h2>Run totals</h2>"]
    parts += _table("Repositories by outcome", [("Category", False), ("Repositories", True)], rows)
    parts.append(f"<p><strong>Total findings:</strong> {counts['findings']}</p>")

    if model.reconciles:
        parts.append(
            '<p class="note">Clean + with findings + skipped + failed = '
            f"{counts['targeted']}, matching the target set. Every repository is "
            "accounted for.</p>"
        )
    else:
        parts.append(
            '<p class="warn"><strong>Warning:</strong> the category counts do not '
            "sum to the target set. Some repository is unaccounted for; treat "
            "these totals as unreliable.</p>"
        )
    return parts


def _errors_section(model: SummaryModel) -> list[str]:
    if not model.run_errors:
        return []
    items = "".join(f"<li>{escape(error)}</li>" for error in model.run_errors)
    return [
        "<h2>Run-level errors</h2>",
        f"<ul>{items}</ul>",
        '<p class="note">Repositories behind these errors were never enumerated '
        "and are not counted above.</p>",
    ]


def _ranking_section(model: SummaryModel) -> list[str]:
    parts = ["<h2>Remediation order</h2>"]
    if not model.ranked:
        return parts + ["<p>No repository has findings.</p>"]

    parts.append(
        '<p class="note">Heaviest first. Weight is dominated by severity, so a '
        "repository with a few high-severity findings outranks one with many "
        "low-severity ones.</p>"
    )
    rows = []
    for index, entry in enumerate(model.ranked, start=1):
        severities = " / ".join(
            str(entry.by_severity[severity]) for severity in Severity.ordered()
        )
        rows.append(
            f'<tr><td class="num">{index}</td>'
            f"<td>{_code(entry.slug)}</td>"
            f'<td class="num">{entry.weight}</td>'
            f'<td class="num">{entry.findings}</td>'
            f"<td>{escape(severities)}</td>"
            f"<td>{_link(entry.report_path)}</td></tr>"
        )
    if model.ranked_omitted:
        rows.append(
            f'<tr><td colspan="6" class="more">… {model.ranked_omitted} more, '
            "see executive-summary.json</td></tr>"
        )
    parts += _table(
        "Repositories with findings, heaviest remediation first",
        [
            ("#", True),
            ("Repository", False),
            ("Weight", True),
            ("Findings", True),
            ("High / Med / Low", False),
            ("Report", False),
        ],
        rows,
    )
    return parts


def _breakdown_section(model: SummaryModel) -> list[str]:
    parts = ["<h2>Findings by search-group and reference label</h2>"]
    if not model.by_match:
        return parts + ["<p>No findings.</p>"]
    rows = [
        f"<tr><td>{_code(row.matched)}</td>"
        f"<td>{escape(row.kind_label)}</td>"
        f"<td>{_severity_pill(row.severity_label)}</td>"
        f'<td class="num">{row.findings}</td>'
        f'<td class="num">{row.repositories}</td></tr>'
        for row in model.by_match
    ]
    parts += _table(
        "Every search-group and reference label that produced a finding",
        [
            ("Matched", False),
            ("Kind", False),
            ("Severity", False),
            ("Findings", True),
            ("Repositories", True),
        ],
        rows,
    )
    return parts


def _values_section(model: SummaryModel) -> list[str]:
    text_rows = [row for row in model.by_match if not row.is_image]
    if not text_rows:
        return []
    rows: list[str] = []
    for row in text_rows:
        rows += _value_rows(row)
    parts = [
        "<h3>What matched</h3>",
        '<p class="note">The distinct values each search-group found, most '
        "frequent first. A case-insensitive group's spellings are counted as one "
        "value and shown in the commonest of them.</p>",
    ]
    parts += _table(
        "Distinct matched values by search-group",
        [
            ("Search-group", False),
            ("Severity", False),
            ("Value", False),
            ("Findings", True),
        ],
        rows,
    )
    return parts


def _value_rows(row: MatchRow) -> list[str]:
    shown, omitted = row.top_values(MAX_VALUES_RENDERED)
    rows = [
        f"<tr><td>{_code(row.matched)}</td>"
        f"<td>{_severity_pill(row.severity_label)}</td>"
        f"<td>{_code(display_value(value.value))}</td>"
        f'<td class="num">{value.findings}</td></tr>'
        for value in shown
    ]
    if omitted:
        rows.append(
            f"<tr><td>{_code(row.matched)}</td>"
            f"<td>{_severity_pill(row.severity_label)}</td>"
            f'<td class="more">… {omitted} more distinct value(s)</td>'
            f'<td class="num">—</td></tr>'
        )
    return rows


def _bands_section(model: SummaryModel) -> list[str]:
    image_rows = [row for row in model.by_match if row.is_image]
    if not image_rows:
        return []
    rows = [
        f"<tr><td>{_code(row.matched)}</td>"
        f"<td>{_band_pill(entry.band.name)}</td>"
        f'<td class="mono">{escape(entry.band.range_text)}</td>'
        f'<td class="num">{entry.findings}</td></tr>'
        for row in image_rows
        for entry in row.bands
    ]
    parts = [
        "<h3>Likeness confidence</h3>",
        f'<p class="note">{escape(BAND_PREAMBLE.format(threshold=model.similarity_threshold))}</p>',
    ]
    parts += _table(
        "Image findings by how close the match was",
        [
            ("Reference label", False),
            ("Confidence", False),
            ("Distance", False),
            ("Findings", True),
        ],
        rows,
    )
    return parts


def _severity_section(model: SummaryModel) -> list[str]:
    rows = [
        f"<tr><td>{_severity_pill(severity.value)}</td>"
        f'<td class="num">{model.by_severity[severity]}</td></tr>'
        for severity in Severity.ordered()
    ]
    parts = ["<h2>Findings by severity</h2>"]
    parts += _table(
        "All findings across every repository",
        [("Severity", False), ("Findings", True)],
        rows,
    )
    return parts


def _not_scanned_section(model: SummaryModel) -> list[str]:
    if not model.not_scanned:
        return []
    rows = [
        f"<tr><td>{_code(entry.slug)}</td>"
        f"<td>{escape(entry.status)}</td>"
        f"<td>{escape(entry.reason) or '—'}</td>"
        f"<td>{_link(entry.report_path)}</td></tr>"
        for entry in model.not_scanned
    ]
    parts = [
        "<h2>Not scanned</h2>",
        '<p class="warn">These repositories were never read. They are '
        "<strong>not</strong> clean — nothing is known about them either way.</p>",
    ]
    parts += _table(
        "Repositories that were never read",
        [("Repository", False), ("Outcome", False), ("Reason", False), ("Report", False)],
        rows,
    )
    return parts
