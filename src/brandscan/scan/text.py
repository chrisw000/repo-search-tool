"""Executing search-groups over a repository's in-scope files.

Every group is treated identically, so a group added by configuration behaves
exactly like a seeded one. Files are read once and every group evaluated
against that single read, because over ~400 repositories re-reading per group
is the difference between a run of hours and a run of days.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from brandscan.config.model import ScanScope, SearchGroup
from brandscan.findings import Finding, MatchType, ScanIssue, UnreadableCause
from brandscan.scan.embedded import EmbeddedImage, find_embedded_images
from brandscan.scan.walker import FileWalker, group_covers

CONTEXT_LINES = 2
MAX_EXCERPT_CHARS = 240


@dataclass
class TextScanResult:
    findings: list[Finding] = field(default_factory=list)
    embedded_images: list[EmbeddedImage] = field(default_factory=list)
    issues: list[ScanIssue] = field(default_factory=list)
    files_scanned: int = 0


def _looks_binary(sample: bytes) -> bool:
    """A NUL byte in the first block is the reliable cheap signal."""
    return b"\x00" in sample


def read_text_lines(path: Path, max_bytes: int) -> list[str] | None:
    """Read a file as text, or return None when it is not text to search.

    Decoding is lenient: this estate holds files in several legacy encodings,
    and a mis-decoded accent is far better than skipping the file.
    """
    try:
        if path.stat().st_size > max_bytes:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if _looks_binary(data[:8192]):
        return None
    return data.decode("utf-8", errors="replace").splitlines()


def _context_for(lines: list[str], index: int) -> list[str]:
    start = max(0, index - CONTEXT_LINES)
    end = min(len(lines), index + CONTEXT_LINES + 1)
    return [lines[i].rstrip() for i in range(start, end)]


def first_surviving_match(line: str, patterns: list, exclusions: list) -> str:
    """The first match on a line that no exclusion vetoes, or "".

    A vetoed match must not end the search: it is skipped and the *next* match
    considered, including one found by a later pattern in the same group. A line
    carrying both a vendor font link and a brand one has to keep the brand one,
    so the veto acts per match rather than per line.

    Where a group declares no exclusions the loop keeps `search`, which stops at
    the first match instead of enumerating every one on the line. That branch is
    not tidiness: this runs over every line of every file of ~400 repositories.
    """
    for pattern in patterns:
        if not exclusions:
            match = pattern.search(line)
            if match:
                return match.group(0)[:MAX_EXCERPT_CHARS]
            continue
        for match in pattern.finditer(line):
            text = match.group(0)
            if not any(exclusion.search(text) for exclusion in exclusions):
                return text[:MAX_EXCERPT_CHARS]
    return ""


def scan_file(
    relative_path: str,
    lines: list[str],
    groups: list[tuple[SearchGroup, list, list]],
) -> list[Finding]:
    """Evaluate every in-scope group against one file's lines.

    At most one finding is recorded per group per line. Several patterns in a
    group commonly describe the same occurrence from different angles — a brand
    name and the markup attribute carrying it — and reporting each separately
    would inflate counts without telling a reader anything new.
    """
    findings: list[Finding] = []
    for group, patterns, exclusions in groups:
        if not group_covers(group, relative_path):
            continue
        for index, line in enumerate(lines):
            excerpt = first_surviving_match(line, patterns, exclusions)
            if not excerpt:
                continue
            findings.append(
                Finding(
                    match_type=MatchType.TEXT,
                    matched=group.name,
                    path=relative_path,
                    line=index + 1,
                    severity=group.severity,
                    context=_context_for(lines, index),
                    excerpt=excerpt,
                    remediation=group.remediation,
                )
            )
    return findings


def scan_text(root: Path, scope: ScanScope, groups: list[SearchGroup]) -> TextScanResult:
    """Run every search-group across one repository."""
    result = TextScanResult()
    compiled = [
        (group, group.compiled_patterns(), group.compiled_exclusions())
        for group in groups
    ]
    walker = FileWalker(root=root, scope=scope)

    for path in walker.iter_files():
        relative = walker.relative(path)
        lines = read_text_lines(path, scope.max_file_bytes)
        if lines is None:
            continue
        result.files_scanned += 1

        result.findings.extend(scan_file(relative, lines, compiled))

        images, failures = find_embedded_images(relative, lines)
        result.embedded_images.extend(images)
        for line_number, reason in failures:
            # A payload that will not even base64-decode is a corrupt image
            # inlined into a text file — the same class of problem as a corrupt
            # image file, and reported the same way.
            result.issues.append(
                ScanIssue(
                    path=relative,
                    reason=reason,
                    line=line_number,
                    cause=UnreadableCause.MALFORMED,
                )
            )

    result.findings.sort(key=lambda finding: finding.sort_key)
    return result
