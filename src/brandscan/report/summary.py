"""The cross-repository rollup.

Answers the three questions the owner of a rebrand actually asks: how much is
there, where is it worst, and what kind of work is it. Its counts reconcile
against the target set, so no repository can go silently unaccounted for.

This module renders Markdown and the JSON sidecar from the computed model in
`summary_model`; `html` renders the third form from the same model. None of the
three aggregates anything itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brandscan.config.model import Config, Severity
from brandscan.report.summary_model import (
    BAND_PREAMBLE,
    MAX_VALUES_JSON,
    MAX_VALUES_RENDERED,
    MatchRow,
    SummaryModel,
    build_summary,
    counts_reconcile,
    display_value,
    ranked,
    totals,
)

__all__ = [
    "build_summary",
    "counts_reconcile",
    "ranked",
    "render_summary",
    "summary_dict",
    "totals",
    "write_summary",
]

def _cell(text: str) -> str:
    """Repository content, made safe to put in a table cell.

    An excerpt is whatever matched a regex in someone's repository. An
    unescaped pipe from a Markdown file silently breaks that row's columns —
    wrong without looking wrong.
    """
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", "")


def _code(text: str) -> str:
    escaped = _cell(text)
    # A backtick inside a code span closes it early; such a value goes bare.
    return escaped if "`" in escaped else f"`{escaped}`"


def _severity_cells(counts: dict[Severity, int]) -> str:
    return " / ".join(str(counts[severity]) for severity in Severity.ordered())


def render_summary(model: SummaryModel) -> str:
    counts = model.totals
    lines: list[str] = [
        "# Brand asset discovery — executive summary",
        "",
        f"Generated {model.generated_at}",
        "",
        "## Run totals",
        "",
        "| Category | Repositories |",
        "| --- | ---: |",
        f"| Targeted | {counts['targeted']} |",
        f"| Scanned | {counts['scanned']} |",
        f"| Clean (scanned, nothing found) | {counts['clean']} |",
        f"| With findings | {counts['with_findings']} |",
        f"| Skipped (not scanned) | {counts['skipped']} |",
        f"| Failed (not scanned) | {counts['failed']} |",
        "",
        f"**Total findings:** {counts['findings']}",
        "",
    ]

    if model.reconciles:
        lines += [
            "Clean + with findings + skipped + failed = "
            f"{counts['targeted']}, matching the target set. Every repository is "
            "accounted for.",
            "",
        ]
    else:
        lines += [
            "> **Warning:** the category counts do not sum to the target set. "
            "Some repository is unaccounted for; treat these totals as unreliable.",
            "",
        ]

    if model.run_errors:
        lines += ["## Run-level errors", ""]
        lines += [f"- {error}" for error in model.run_errors]
        lines += [
            "",
            "Repositories behind these errors were never enumerated and are not "
            "counted above.",
            "",
        ]

    lines += _ranking_section(model)
    lines += _breakdown_sections(model)
    lines += _not_scanned_section(model)
    return "\n".join(lines).rstrip() + "\n"


def _ranking_section(model: SummaryModel) -> list[str]:
    lines = [
        "## Remediation order",
        "",
    ]
    if not model.ranked:
        return lines + ["No repository has findings.", ""]

    lines += [
        "Heaviest first. Weight is dominated by severity, so a repository with a "
        "few high-severity findings outranks one with many low-severity ones.",
        "",
        "| # | Repository | Weight | Findings | High / Med / Low | Report |",
        "| ---: | --- | ---: | ---: | --- | --- |",
    ]
    for index, entry in enumerate(model.ranked, start=1):
        link = f"[report]({entry.report_path})" if entry.report_path else "—"
        lines.append(
            f"| {index} | `{entry.slug}` | {entry.weight} | "
            f"{entry.findings} | {_severity_cells(entry.by_severity)} | {link} |"
        )
    if model.ranked_omitted:
        lines.append(
            f"| | _… {model.ranked_omitted} more, see executive-summary.json_ "
            "| | | | |"
        )
    lines.append("")
    return lines


def _breakdown_sections(model: SummaryModel) -> list[str]:
    lines = ["## Findings by search-group and reference label", ""]
    if not model.by_match:
        lines += ["No findings.", ""]
    else:
        lines += [
            "| Matched | Kind | Severity | Findings | Repositories |",
            "| --- | --- | --- | ---: | ---: |",
        ]
        for row in model.by_match:
            lines.append(
                f"| {_code(row.matched)} | {row.kind_label} | {row.severity_label} | "
                f"{row.findings} | {row.repositories} |"
            )
        lines.append("")
        lines += _values_section(model)
        lines += _bands_section(model)

    lines += [
        "## Findings by severity",
        "",
        "| Severity | Findings |",
        "| --- | ---: |",
    ]
    for severity in Severity.ordered():
        lines.append(f"| {severity.value} | {model.by_severity[severity]} |")
    lines.append("")
    return lines


def _values_section(model: SummaryModel) -> list[str]:
    if not model.has_value_rows:
        return []
    lines = [
        "### What matched",
        "",
        "The distinct values each search-group found, most frequent first. A "
        "case-insensitive group's spellings are counted as one value and shown "
        "in the commonest of them.",
        "",
        "| Search-group | Severity | Value | Findings |",
        "| --- | --- | --- | ---: |",
    ]
    for row in _text_rows(model):
        shown, omitted = row.top_values(MAX_VALUES_RENDERED)
        for value in shown:
            lines.append(
                f"| {_code(row.matched)} | {row.severity_label} | "
                f"{_code(display_value(value.value))} | {value.findings} |"
            )
        if omitted:
            lines.append(
                f"| {_code(row.matched)} | {row.severity_label} | "
                f"_… {omitted} more distinct value(s)_ | — |"
            )
    lines.append("")
    return lines


def _bands_section(model: SummaryModel) -> list[str]:
    if not model.has_image_rows:
        return []
    lines = [
        "### Likeness confidence",
        "",
        BAND_PREAMBLE.format(threshold=model.similarity_threshold),
        "",
        "| Reference label | Confidence | Distance | Findings |",
        "| --- | --- | --- | ---: |",
    ]
    for row in _image_rows(model):
        for entry in row.bands:
            lines.append(
                f"| {_code(row.matched)} | {entry.band.name} | "
                f"{entry.band.range_text} | {entry.findings} |"
            )
    lines.append("")
    return lines


def _text_rows(model: SummaryModel) -> list[MatchRow]:
    return [row for row in model.by_match if not row.is_image]


def _image_rows(model: SummaryModel) -> list[MatchRow]:
    return [row for row in model.by_match if row.is_image]


def _not_scanned_section(model: SummaryModel) -> list[str]:
    if not model.not_scanned:
        return []
    lines = [
        "## Not scanned",
        "",
        "These repositories were never read. They are **not** clean — nothing is "
        "known about them either way.",
        "",
        "| Repository | Outcome | Reason | Report |",
        "| --- | --- | --- | --- |",
    ]
    for entry in model.not_scanned:
        link = f"[report]({entry.report_path})" if entry.report_path else "—"
        lines.append(
            f"| `{entry.slug}` | {entry.status} | {_cell(entry.reason) or '—'} | {link} |"
        )
    lines.append("")
    return lines


def summary_dict(model: SummaryModel) -> dict[str, Any]:
    return {
        "generated_at": model.generated_at,
        "totals": dict(model.totals),
        "counts_reconcile": model.reconciles,
        "similarity_threshold": model.similarity_threshold,
        "confidence_bands": [
            {"name": band.name, "distance": band.range_text} for band in model.bands
        ],
        "by_match": {
            row.matched: {
                "kind": row.kind.value,
                "findings": row.findings,
                "repositories": row.repositories,
                "severity": row.severity_label,
                "values": [
                    {"value": value.value, "findings": value.findings}
                    for value in row.values[:MAX_VALUES_JSON]
                ],
                "values_omitted": max(0, len(row.values) - MAX_VALUES_JSON),
                "bands": [
                    {
                        "name": entry.band.name,
                        "distance": entry.band.range_text,
                        "findings": entry.findings,
                    }
                    for entry in row.bands
                ],
            }
            for row in model.by_match
        },
        "by_severity": {s.value: c for s, c in model.by_severity.items()},
        "run_errors": list(model.run_errors),
        "repositories": [
            {
                "slug": entry.slug,
                "status": entry.status,
                "findings": entry.findings,
                "remediation_weight": entry.weight,
                "reason": entry.reason,
                "report": entry.report_path,
            }
            for entry in model.repositories
        ],
    }


def write_summary(
    results: list,
    run_errors: list[str],
    config: Config,
    markdown_path: Path,
    json_path: Path,
    html_path: Path,
) -> None:
    """Write all three forms of the summary from one computed model."""
    from brandscan.report.html import render_summary_html

    model = build_summary(results, run_errors, config)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_summary(model), encoding="utf-8")
    html_path.write_text(render_summary_html(model), encoding="utf-8")
    json_path.write_text(
        json.dumps(summary_dict(model), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
