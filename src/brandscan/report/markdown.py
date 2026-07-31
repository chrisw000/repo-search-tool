"""The per-repository report.

This is the hand-off: an AI coding agent reads it and performs the fixes. That
makes its structure a contract rather than a presentation choice, so findings
are grouped into remediation tasks — each stating what was found, where, and
what to change — rather than dumped as a flat list of matches.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from brandscan.findings import Finding, MatchType, ScanIssue, UnreadableCause
from brandscan.results import RepoResult, RepoStatus

MAX_LISTED_PER_TASK = 50


def _fence(lines: list[str]) -> list[str]:
    """Fence context lines, using a longer fence than anything they contain.

    Context is copied verbatim out of source files, and Markdown source files
    legitimately contain fences of their own.
    """
    if not lines:
        return []
    runs = [len(match.group(0)) for line in lines for match in re.finditer(r"`+", line)]
    ticks = "`" * max(3, max(runs, default=0) + 1)
    return [ticks, *lines, ticks]


def _task_groups(findings: list[Finding]) -> list[tuple[MatchType, str, list[Finding]]]:
    """Collect findings into remediation tasks, heaviest first.

    One task per (match type, matched thing): every occurrence of the old
    wordmark is one job, not thirty unrelated ones.
    """
    buckets: dict[tuple[MatchType, str], list[Finding]] = {}
    for finding in findings:
        buckets.setdefault((finding.match_type, finding.matched), []).append(finding)

    ordered = sorted(
        buckets.items(),
        key=lambda item: (
            -max(f.severity.weight for f in item[1]),
            -len(item[1]),
            item[0][1],
        ),
    )
    return [(key[0], key[1], value) for key, value in ordered]


def _status_line(result: RepoResult) -> str:
    if result.status is RepoStatus.CLEAN:
        return "**Status:** clean — scanned successfully, no brand residue found."
    if result.status is RepoStatus.FINDINGS:
        return f"**Status:** {len(result.findings)} finding(s) to remediate."
    if result.status is RepoStatus.SKIPPED:
        return "**Status:** SKIPPED — this repository was not scanned."
    return "**Status:** FAILED — this repository was not scanned."


def _header(result: RepoResult) -> list[str]:
    target = result.target
    provenance = result.provenance
    lines = [
        f"# Brand remediation — {target.org}/{target.name}",
        "",
        f"**Repository:** `{target.slug}`  ",
        f"**Branch:** `{provenance.branch or 'n/a'}`  ",
        f"**Commit scanned:** `{provenance.commit_sha or 'n/a'}`  ",
        _status_line(result),
        "",
    ]
    if result.reason:
        lines += [f"**Reason:** {result.reason}", ""]
    return lines


def _not_scanned_body(result: RepoResult) -> list[str]:
    what = "skipped" if result.status is RepoStatus.SKIPPED else "failed during acquisition"
    return [
        "## No assessment was made",
        "",
        f"This repository was {what}, so its contents were never read. "
        "It is **not** clean — nothing is known about it either way. Resolve the "
        "reason above and re-run to assess it.",
        "",
    ]


def _clean_body(result: RepoResult) -> list[str]:
    """State cleanliness against what was actually read, not against the repository.

    With unread inputs present, "scanned in full" would be false, and a reader
    who stopped at this section would carry away the wrong conclusion. The
    findings verdict still stands — nothing was found in what was read — but its
    scope has to be stated alongside it.
    """
    if result.issues:
        return [
            "## Nothing to change in what was read",
            "",
            "No text-pattern or image match was found in the content this scan "
            f"could read. {len(result.issues)} input(s) could not be read and "
            "were **not** assessed — see below. This repository is clean on "
            "findings, not verified in full.",
            "",
        ]
    return [
        "## Nothing to change",
        "",
        "This repository was scanned in full and no text-pattern or image match "
        "was found. No remediation is required.",
        "",
    ]


def _findings_body(result: RepoResult) -> list[str]:
    lines: list[str] = ["## What to change", ""]
    tasks = _task_groups(result.findings)

    lines += [
        f"{len(tasks)} remediation task(s), ordered by severity. Each section "
        "states what was found, what to change, and every location.",
        "",
    ]

    for index, (match_type, matched, findings) in enumerate(tasks, start=1):
        severity = max((f.severity for f in findings), key=lambda s: s.weight)
        kind = "image match" if match_type is MatchType.IMAGE else "text match"
        heading = (
            f"### {index}. `{matched}` — {kind}, severity {severity.value} "
            f"({len(findings)} occurrence(s))"
        )
        lines += [heading, ""]

        remediation = next((f.remediation for f in findings if f.remediation), "")
        if remediation:
            lines += [f"**What to do:** {remediation}", ""]

        if match_type is MatchType.IMAGE:
            lines += _image_task_body(findings)
        else:
            lines += _text_task_body(findings)

    return lines


def _image_task_body(findings: list[Finding]) -> list[str]:
    lines = [
        "| File | Distance | Inlined in | Link |",
        "| --- | --- | --- | --- |",
    ]
    for finding in findings[:MAX_LISTED_PER_TASK]:
        link = f"[view]({finding.permalink})" if finding.permalink else "—"
        inlined = (
            f"`{finding.embedded_in}` line {finding.line}" if finding.embedded_in else "—"
        )
        lines.append(
            f"| `{finding.path}` | {finding.distance} | {inlined} | {link} |"
        )
    if len(findings) > MAX_LISTED_PER_TASK:
        lines.append(
            f"| _… {len(findings) - MAX_LISTED_PER_TASK} more, see report.json_ | | | |"
        )
    lines.append("")
    return lines


def _text_task_body(findings: list[Finding]) -> list[str]:
    lines: list[str] = []
    for finding in findings[:MAX_LISTED_PER_TASK]:
        location = f"`{finding.path}`" + (f" line {finding.line}" if finding.line else "")
        link = f" — [view]({finding.permalink})" if finding.permalink else ""
        lines.append(f"- {location}{link}")
        if finding.excerpt:
            lines.append(f"  - matched: `{finding.excerpt}`")
        if finding.context:
            lines += ["  " + entry for entry in _fence(finding.context)]
    if len(findings) > MAX_LISTED_PER_TASK:
        lines.append(
            f"- _… {len(findings) - MAX_LISTED_PER_TASK} more occurrence(s), "
            "see report.json_"
        )
    lines.append("")
    return lines


def _issue_groups(issues: list[ScanIssue]) -> list[tuple[UnreadableCause | None, list[ScanIssue]]]:
    """Group unread inputs by cause, in the order an operator should read them.

    A pointer to an unfetched asset, a committed placeholder, and a corrupt file
    have nothing in common but their symptom. Presenting them as one list makes
    the whole section look like the same undifferentiated defect, which is how a
    reader learns to skip it.
    """
    buckets: dict[UnreadableCause | None, list[ScanIssue]] = {}
    for issue in issues:
        buckets.setdefault(issue.cause, []).append(issue)

    order = list(UnreadableCause)
    return sorted(
        buckets.items(),
        key=lambda item: order.index(item[0]) if item[0] is not None else len(order),
    )


def _issues_body(result: RepoResult) -> list[str]:
    if not result.issues:
        return []
    lines = [
        "## Files that could not be read",
        "",
        f"{len(result.issues)} input(s) were not assessed. They may still contain "
        "brand residue, so treat this section as unassessed rather than clean. "
        "Each group states what would be needed to assess it.",
        "",
    ]

    remaining = MAX_LISTED_PER_TASK
    for cause, issues in _issue_groups(result.issues):
        heading = cause.heading if cause else "Not read"
        lines += [f"### {heading} ({len(issues)})", ""]
        if cause:
            lines += [f"**What to do:** {cause.remediation}", ""]
        for issue in issues[:remaining]:
            where = f"`{issue.path}`" + (f" line {issue.line}" if issue.line else "")
            lines.append(f"- {where} — {issue.reason}")
        if len(issues) > remaining:
            lines.append(f"- _… {len(issues) - remaining} more, see report.json_")
        remaining = max(0, remaining - len(issues))
        lines.append("")
    return lines


def _minimum_size_lines(result: RepoResult) -> list[str]:
    """What the size gate was set to, and what it cost.

    Stated even when it cost nothing: `0` ruled out says every image in this
    repository was assessed, which is a different claim from silence.
    """
    minimum = result.provenance.min_image_dimension
    if minimum <= 0:
        return ["- **Minimum image size:** none (every image assessed)"]
    return [
        f"- **Minimum image size:** {minimum}×{minimum} px",
        f"- **Images below the minimum:** {result.images_below_minimum} "
        "(read, too small to assess)",
    ]


def _provenance_body(result: RepoResult) -> list[str]:
    provenance = result.provenance
    threshold_note = " (default)" if provenance.threshold_was_defaulted else " (configured)"
    return [
        "## Provenance",
        "",
        f"- **Tool version:** {provenance.tool_version}",
        f"- **Scanned at:** {provenance.scanned_at}",
        f"- **Commit scanned:** `{provenance.commit_sha or 'n/a'}`",
        f"- **Branch:** `{provenance.branch or 'n/a'}`",
        f"- **Similarity threshold:** {provenance.similarity_threshold}{threshold_note}",
        f"- **Matching strategy:** {provenance.matching_strategy or 'n/a'}",
        "- **Search-groups executed:** "
        + (", ".join(f"`{g}`" for g in provenance.search_groups) or "none"),
        "- **Reference labels searched:** "
        + (", ".join(f"`{label}`" for label in provenance.reference_labels) or "none"),
        f"- **Files scanned:** {result.files_scanned}",
        f"- **Images examined:** {result.images_examined}",
        *_minimum_size_lines(result),
        "",
    ]


def render_repo_markdown(result: RepoResult) -> str:
    """Render one repository's report."""
    lines = _header(result)

    if result.status in (RepoStatus.SKIPPED, RepoStatus.FAILED):
        lines += _not_scanned_body(result)
    elif result.status is RepoStatus.CLEAN:
        lines += _clean_body(result)
    else:
        lines += _findings_body(result)

    lines += _issues_body(result)
    lines += _provenance_body(result)
    return "\n".join(lines).rstrip() + "\n"


def write_repo_report(result: RepoResult, markdown_path: Path, json_path: Path) -> None:
    """Write both forms of one repository's report.

    The sidecar is generated from the same `RepoResult`, so it cannot omit a
    finding the Markdown shows.
    """
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_repo_markdown(result), encoding="utf-8")
    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
