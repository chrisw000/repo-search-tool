"""What a run knows about one repository once it is finished with it.

`RepoStatus` deliberately separates CLEAN from SKIPPED and FAILED. "No
findings" and "never read" look identical in a bare count, and conflating them
would let a rebrand declare a repository done that was never opened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from brandscan.acquisition.models import RepoTarget
from brandscan.config.model import Severity
from brandscan.findings import Finding, ScanIssue


class RepoStatus(str, Enum):
    CLEAN = "clean"
    FINDINGS = "findings"
    SKIPPED = "skipped"
    FAILED = "failed"

    @property
    def was_scanned(self) -> bool:
        return self in (RepoStatus.CLEAN, RepoStatus.FINDINGS)


@dataclass
class Provenance:
    """The conditions a report was produced under.

    Without this a report is unreproducible, and a stale report is
    indistinguishable from a fresh one.
    """

    tool_version: str
    scanned_at: str
    search_groups: list[str] = field(default_factory=list)
    reference_labels: list[str] = field(default_factory=list)
    similarity_threshold: int = 0
    threshold_was_defaulted: bool = True
    # The size gate a run was taken under. Recorded for the same reason the
    # threshold is: two reports that do not state it cannot be compared, because
    # the count of images examined means something different under each.
    min_image_dimension: int = 0
    matching_strategy: str = ""
    commit_sha: str | None = None
    branch: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_version": self.tool_version,
            "scanned_at": self.scanned_at,
            "search_groups": list(self.search_groups),
            "reference_labels": list(self.reference_labels),
            "similarity_threshold": self.similarity_threshold,
            "threshold_source": "default" if self.threshold_was_defaulted else "configured",
            "min_image_dimension": self.min_image_dimension,
            "matching_strategy": self.matching_strategy,
            "commit_sha": self.commit_sha,
            "branch": self.branch,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Provenance":
        return cls(
            tool_version=payload.get("tool_version", ""),
            scanned_at=payload.get("scanned_at", ""),
            search_groups=list(payload.get("search_groups", [])),
            reference_labels=list(payload.get("reference_labels", [])),
            similarity_threshold=int(payload.get("similarity_threshold", 0)),
            threshold_was_defaulted=payload.get("threshold_source", "default") == "default",
            min_image_dimension=int(payload.get("min_image_dimension", 0)),
            matching_strategy=payload.get("matching_strategy", ""),
            commit_sha=payload.get("commit_sha"),
            branch=payload.get("branch"),
        )


@dataclass
class RepoResult:
    """One repository's complete outcome, and the basis of its report."""

    target: RepoTarget
    status: RepoStatus
    provenance: Provenance
    findings: list[Finding] = field(default_factory=list)
    issues: list[ScanIssue] = field(default_factory=list)
    reason: str = ""
    files_scanned: int = 0
    images_examined: int = 0
    # Read, never assessed: too small to carry a layout. Kept apart from both
    # `images_examined` and `issues`, because it is neither a look that found
    # nothing nor a file that could not be read.
    images_below_minimum: int = 0
    report_path: str = ""

    @property
    def remediation_weight(self) -> int:
        """Triage weight: severity dominates raw count.

        A repository with one high-severity finding outranks one with a pile of
        low-severity ones, because that is the order the work should be done in.
        """
        return sum(finding.severity.weight for finding in self.findings)

    def counts_by_severity(self) -> dict[Severity, int]:
        counts = {severity: 0 for severity in Severity.ordered()}
        for finding in self.findings:
            counts[finding.severity] += 1
        return counts

    def counts_by_match(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.matched] = counts.get(finding.matched, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": {
                "host": self.target.host,
                "org": self.target.org,
                "name": self.target.name,
                "slug": self.target.slug,
            },
            "status": self.status.value,
            "reason": self.reason,
            "provenance": self.provenance.to_dict(),
            "counts": {
                "findings": len(self.findings),
                "files_scanned": self.files_scanned,
                "images_examined": self.images_examined,
                "images_below_minimum": self.images_below_minimum,
                "by_severity": {
                    severity.value: count
                    for severity, count in self.counts_by_severity().items()
                },
                "by_match": self.counts_by_match(),
            },
            "findings": [finding.to_dict() for finding in self.findings],
            "issues": [issue.to_dict() for issue in self.issues],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any], target: RepoTarget) -> "RepoResult":
        """Rebuild a result from its own JSON sidecar.

        This is how a resumed run accounts for repositories completed by an
        earlier one: their reports are already on disk, and the sidecar holds
        everything the executive summary needs.
        """
        counts = payload.get("counts", {})
        return cls(
            target=target,
            status=RepoStatus(payload["status"]),
            provenance=Provenance.from_dict(payload.get("provenance", {})),
            findings=[Finding.from_dict(entry) for entry in payload.get("findings", [])],
            issues=[ScanIssue.from_dict(entry) for entry in payload.get("issues", [])],
            reason=payload.get("reason", ""),
            files_scanned=int(counts.get("files_scanned", 0)),
            images_examined=int(counts.get("images_examined", 0)),
            images_below_minimum=int(counts.get("images_below_minimum", 0)),
        )
