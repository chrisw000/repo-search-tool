"""The cross-repository rollup.

Answers the three questions the owner of a rebrand actually asks: how much is
there, where is it worst, and what kind of work is it. Its counts reconcile
against the target set, so no repository can go silently unaccounted for.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brandscan.config.model import Severity
from brandscan.findings import MatchType
from brandscan.results import RepoResult, RepoStatus

MAX_RANKED = 200


def totals(results: list[RepoResult]) -> dict[str, int]:
    """Category counts that must sum to the size of the target set."""
    counts = {
        "targeted": len(results),
        "scanned": 0,
        "clean": 0,
        "with_findings": 0,
        "skipped": 0,
        "failed": 0,
        "findings": 0,
    }
    for result in results:
        if result.status is RepoStatus.CLEAN:
            counts["clean"] += 1
            counts["scanned"] += 1
        elif result.status is RepoStatus.FINDINGS:
            counts["with_findings"] += 1
            counts["scanned"] += 1
        elif result.status is RepoStatus.SKIPPED:
            counts["skipped"] += 1
        else:
            counts["failed"] += 1
        counts["findings"] += len(result.findings)
    return counts


def counts_reconcile(counts: dict[str, int]) -> bool:
    accounted = counts["clean"] + counts["with_findings"] + counts["skipped"] + counts["failed"]
    return accounted == counts["targeted"]


def ranked(results: list[RepoResult]) -> list[RepoResult]:
    """Repositories with findings, heaviest remediation first.

    Only repositories that actually have findings appear here; clean ones stay
    in the totals rather than padding a triage list.
    """
    with_findings = [r for r in results if r.status is RepoStatus.FINDINGS]
    return sorted(
        with_findings,
        key=lambda r: (-r.remediation_weight, -len(r.findings), r.target.slug),
    )


def by_match(results: list[RepoResult]) -> dict[str, dict[str, Any]]:
    """Findings per search-group and per reference label, across all repos."""
    breakdown: dict[str, dict[str, Any]] = {}
    for result in results:
        for finding in result.findings:
            entry = breakdown.setdefault(
                finding.matched,
                {"kind": finding.match_type.value, "findings": 0, "repositories": set()},
            )
            entry["findings"] += 1
            entry["repositories"].add(result.target.slug)
    return breakdown


def by_severity(results: list[RepoResult]) -> dict[Severity, int]:
    counts = {severity: 0 for severity in Severity.ordered()}
    for result in results:
        for finding in result.findings:
            counts[finding.severity] += 1
    return counts


def summary_dict(results: list[RepoResult], run_errors: list[str]) -> dict[str, Any]:
    counts = totals(results)
    match_breakdown = {
        name: {
            "kind": entry["kind"],
            "findings": entry["findings"],
            "repositories": len(entry["repositories"]),
        }
        for name, entry in sorted(
            by_match(results).items(), key=lambda item: -item[1]["findings"]
        )
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totals": counts,
        "counts_reconcile": counts_reconcile(counts),
        "by_match": match_breakdown,
        "by_severity": {s.value: c for s, c in by_severity(results).items()},
        "run_errors": list(run_errors),
        "repositories": [
            {
                "slug": result.target.slug,
                "status": result.status.value,
                "findings": len(result.findings),
                "remediation_weight": result.remediation_weight,
                "reason": result.reason,
                "report": result.report_path,
            }
            for result in results
        ],
    }


def _severity_cells(result: RepoResult) -> str:
    counts = result.counts_by_severity()
    return " / ".join(str(counts[severity]) for severity in Severity.ordered())


def render_summary(results: list[RepoResult], run_errors: list[str]) -> str:
    counts = totals(results)
    lines: list[str] = [
        "# Brand asset discovery — executive summary",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
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

    if counts_reconcile(counts):
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

    if run_errors:
        lines += ["## Run-level errors", ""]
        lines += [f"- {error}" for error in run_errors]
        lines += [
            "",
            "Repositories behind these errors were never enumerated and are not "
            "counted above.",
            "",
        ]

    lines += _ranking_section(results)
    lines += _breakdown_sections(results)
    lines += _not_scanned_section(results)
    return "\n".join(lines).rstrip() + "\n"


def _ranking_section(results: list[RepoResult]) -> list[str]:
    ordered = ranked(results)
    lines = [
        "## Remediation order",
        "",
    ]
    if not ordered:
        return lines + ["No repository has findings.", ""]

    lines += [
        "Heaviest first. Weight is dominated by severity, so a repository with a "
        "few high-severity findings outranks one with many low-severity ones.",
        "",
        "| # | Repository | Weight | Findings | High / Med / Low | Report |",
        "| ---: | --- | ---: | ---: | --- | --- |",
    ]
    for index, result in enumerate(ordered[:MAX_RANKED], start=1):
        link = f"[report]({result.report_path})" if result.report_path else "—"
        lines.append(
            f"| {index} | `{result.target.slug}` | {result.remediation_weight} | "
            f"{len(result.findings)} | {_severity_cells(result)} | {link} |"
        )
    if len(ordered) > MAX_RANKED:
        lines.append(
            f"| | _… {len(ordered) - MAX_RANKED} more, see executive-summary.json_ "
            "| | | | |"
        )
    lines.append("")
    return lines


def _breakdown_sections(results: list[RepoResult]) -> list[str]:
    breakdown = by_match(results)
    lines = ["## Findings by search-group and reference label", ""]
    if not breakdown:
        lines += ["No findings.", ""]
    else:
        lines += [
            "| Matched | Kind | Findings | Repositories |",
            "| --- | --- | ---: | ---: |",
        ]
        for name, entry in sorted(breakdown.items(), key=lambda item: -item[1]["findings"]):
            kind = (
                "reference label" if entry["kind"] == MatchType.IMAGE.value else "search-group"
            )
            lines.append(
                f"| `{name}` | {kind} | {entry['findings']} | {len(entry['repositories'])} |"
            )
        lines.append("")

    severities = by_severity(results)
    lines += [
        "## Findings by severity",
        "",
        "| Severity | Findings |",
        "| --- | ---: |",
    ]
    for severity in Severity.ordered():
        lines.append(f"| {severity.value} | {severities[severity]} |")
    lines.append("")
    return lines


def _not_scanned_section(results: list[RepoResult]) -> list[str]:
    not_scanned = [r for r in results if not r.status.was_scanned]
    if not not_scanned:
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
    for result in sorted(not_scanned, key=lambda r: r.target.slug):
        link = f"[report]({result.report_path})" if result.report_path else "—"
        reason = result.reason.replace("|", "\\|") or "—"
        lines.append(
            f"| `{result.target.slug}` | {result.status.value} | {reason} | {link} |"
        )
    lines.append("")
    return lines


def write_summary(
    results: list[RepoResult], run_errors: list[str], markdown_path: Path, json_path: Path
) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_summary(results, run_errors), encoding="utf-8")
    json_path.write_text(
        json.dumps(summary_dict(results, run_errors), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
