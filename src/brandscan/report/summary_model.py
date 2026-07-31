"""The computed shape of the executive summary.

One model stands behind all three renderings — Markdown, HTML and the JSON
sidecar. No renderer computes an aggregate of its own and none derives its
content from another's output, because the contract is that the forms agree:
a reader who opens the HTML must not be reading a different run from the one
who opens the Markdown.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from brandscan.config.model import (
    ConfidenceBand,
    Config,
    Severity,
    band_for,
    reachable_bands,
)
from brandscan.findings import MatchType
from brandscan.results import RepoResult, RepoStatus

MAX_RANKED = 200

# What a reader can take in. Past the first handful of matched values the table
# has stopped telling them what the group catches, so the rendered documents cap
# it and say how many were dropped; the sidecar keeps more for anyone scripting.
MAX_VALUES_RENDERED = 10
MAX_VALUES_JSON = 50

# Excerpts arrive capped at 240 characters, which is far wider than a column.
MAX_VALUE_CHARS = 60

NO_EXCERPT = "(no excerpt recorded)"

BAND_PREAMBLE = (
    "Bands are absolute in perceptual-hash distance, so a band means the same "
    "thing in every run. This run's similarity threshold was {threshold}; a "
    "band lying wholly beyond it is omitted, because no finding could have "
    "reached it. A band that is shown but empty is a result in its own right."
)


def display_value(text: str) -> str:
    """A matched value narrowed to something a table cell can hold."""
    if not text:
        return NO_EXCERPT
    if len(text) <= MAX_VALUE_CHARS:
        return text
    return text[: MAX_VALUE_CHARS - 1] + "…"


@dataclass(frozen=True)
class MatchedValue:
    """One distinct thing a search-group actually matched."""

    value: str
    findings: int


@dataclass(frozen=True)
class BandCount:
    band: ConfidenceBand
    findings: int


@dataclass
class MatchRow:
    """One search-group or reference label, and what it found.

    A text row expands into the values it matched; an image row expands into
    the confidence bands its findings fell in, because for an image the
    meaningful sub-division is how close the match was, not what string it was.
    """

    matched: str
    kind: MatchType
    findings: int
    repositories: int
    severities: list[Severity] = field(default_factory=list)
    values: list[MatchedValue] = field(default_factory=list)
    bands: list[BandCount] = field(default_factory=list)

    @property
    def is_image(self) -> bool:
        return self.kind is MatchType.IMAGE

    @property
    def kind_label(self) -> str:
        return "reference label" if self.is_image else "search-group"

    @property
    def severity_label(self) -> str:
        """The severity this row's findings carry.

        Taken from the findings rather than looked up in configuration: the
        finding already carries the group's configured severity, copied at scan
        time, and re-deriving it would let a row disagree with what it counts.
        Uniform by construction — if that ever stops being true, every severity
        present is shown rather than one of them being picked silently.
        """
        return ", ".join(severity.value for severity in self.severities) or "—"

    def top_values(self, limit: int = MAX_VALUES_RENDERED) -> tuple[list[MatchedValue], int]:
        """The most frequent values, and how many were left out."""
        return self.values[:limit], max(0, len(self.values) - limit)


@dataclass(frozen=True)
class RankedRepo:
    slug: str
    weight: int
    findings: int
    by_severity: dict[Severity, int]
    report_path: str


@dataclass(frozen=True)
class NotScannedRepo:
    slug: str
    status: str
    reason: str
    report_path: str


@dataclass(frozen=True)
class RepoEntry:
    """One repository as the sidecar records it."""

    slug: str
    status: str
    findings: int
    weight: int
    reason: str
    report_path: str


@dataclass
class SummaryModel:
    generated_at: str
    totals: dict[str, int]
    reconciles: bool
    run_errors: list[str] = field(default_factory=list)
    ranked: list[RankedRepo] = field(default_factory=list)
    ranked_omitted: int = 0
    by_match: list[MatchRow] = field(default_factory=list)
    by_severity: dict[Severity, int] = field(default_factory=dict)
    not_scanned: list[NotScannedRepo] = field(default_factory=list)
    repositories: list[RepoEntry] = field(default_factory=list)
    similarity_threshold: int = 0
    bands: list[ConfidenceBand] = field(default_factory=list)

    @property
    def has_image_rows(self) -> bool:
        return any(row.is_image for row in self.by_match)

    @property
    def has_value_rows(self) -> bool:
        return any(not row.is_image for row in self.by_match)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def by_severity(results: list[RepoResult]) -> dict[Severity, int]:
    counts = {severity: 0 for severity in Severity.ordered()}
    for result in results:
        for finding in result.findings:
            counts[finding.severity] += 1
    return counts


def _fold_key(excerpt: str, case_sensitive: bool) -> str:
    """How two spellings are judged to be the same matched value.

    A case-insensitive group is one whose author declared that case does not
    distinguish a match, so folding is what they asked for; a case-sensitive
    group's author declared the opposite, and folding there would destroy the
    distinction they configured.
    """
    return excerpt if case_sensitive else excerpt.casefold()


def _matched_values(spellings: dict[str, Counter[str]]) -> list[MatchedValue]:
    """Distinct values, most frequent first, shown in their commonest spelling."""
    values = []
    for counted in spellings.values():
        total = sum(counted.values())
        display = sorted(counted.items(), key=lambda item: (-item[1], item[0]))[0][0]
        values.append(MatchedValue(value=display or NO_EXCERPT, findings=total))
    return sorted(values, key=lambda value: (-value.findings, value.value))


def _match_rows(results: list[RepoResult], config: Config, threshold: int) -> list[MatchRow]:
    findings_by_match: dict[str, int] = {}
    kinds: dict[str, MatchType] = {}
    repositories: dict[str, set[str]] = {}
    severities: dict[str, set[Severity]] = {}
    spellings: dict[str, dict[str, Counter[str]]] = {}
    distances: dict[str, list[int]] = {}

    for result in results:
        for finding in result.findings:
            name = finding.matched
            findings_by_match[name] = findings_by_match.get(name, 0) + 1
            kinds.setdefault(name, finding.match_type)
            repositories.setdefault(name, set()).add(result.target.slug)
            severities.setdefault(name, set()).add(finding.severity)

            if finding.match_type is MatchType.IMAGE:
                # A finding recorded without a distance cannot be banded, and is
                # left out of the distribution rather than being assigned a
                # confidence it was never measured to have.
                if finding.distance is not None:
                    distances.setdefault(name, []).append(finding.distance)
                continue

            group = config.group(name)
            # An unknown group — a resumed run whose configuration has since
            # changed — folds, which is the common case and the safer default.
            case_sensitive = bool(group and group.case_sensitive)
            key = _fold_key(finding.excerpt, case_sensitive)
            spellings.setdefault(name, {}).setdefault(key, Counter())[finding.excerpt] += 1

    bands = reachable_bands(threshold)
    rows = []
    for name, count in findings_by_match.items():
        kind = kinds[name]
        row = MatchRow(
            matched=name,
            kind=kind,
            findings=count,
            repositories=len(repositories[name]),
            severities=[s for s in Severity.ordered() if s in severities[name]],
        )
        if kind is MatchType.IMAGE:
            banded = Counter(band_for(d).name for d in distances.get(name, []))
            row.bands = [BandCount(band=band, findings=banded[band.name]) for band in bands]
        else:
            row.values = _matched_values(spellings.get(name, {}))
        rows.append(row)

    return sorted(rows, key=lambda row: (-row.findings, row.matched))


def build_summary(
    results: list[RepoResult], run_errors: list[str], config: Config
) -> SummaryModel:
    """Compute everything the three renderings present.

    Configuration is needed for the two things no finding carries: the
    similarity threshold, which governs which confidence bands a run could
    reach at all, and each group's case sensitivity, which governs whether two
    spellings are one matched value.
    """
    counts = totals(results)
    threshold = config.similarity_threshold
    order = ranked(results)

    return SummaryModel(
        generated_at=_now(),
        totals=counts,
        reconciles=counts_reconcile(counts),
        run_errors=list(run_errors),
        ranked=[
            RankedRepo(
                slug=result.target.slug,
                weight=result.remediation_weight,
                findings=len(result.findings),
                by_severity=result.counts_by_severity(),
                report_path=result.report_path,
            )
            for result in order[:MAX_RANKED]
        ],
        ranked_omitted=max(0, len(order) - MAX_RANKED),
        by_match=_match_rows(results, config, threshold),
        by_severity=by_severity(results),
        not_scanned=[
            NotScannedRepo(
                slug=result.target.slug,
                status=result.status.value,
                reason=result.reason,
                report_path=result.report_path,
            )
            for result in sorted(
                (r for r in results if not r.status.was_scanned),
                key=lambda r: r.target.slug,
            )
        ],
        repositories=[
            RepoEntry(
                slug=result.target.slug,
                status=result.status.value,
                findings=len(result.findings),
                weight=result.remediation_weight,
                reason=result.reason,
                report_path=result.report_path,
            )
            for result in results
        ],
        similarity_threshold=threshold,
        bands=list(reachable_bands(threshold)),
    )
