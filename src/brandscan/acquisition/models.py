"""The acquisition vocabulary shared by enumeration, cloning, and reporting."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class AcquisitionOutcome(str, Enum):
    """How acquisition ended for one repository.

    `SKIPPED` and `FAILED` are distinct from each other and from a clean scan:
    a repository that was never read must never be presented as having no
    findings.
    """

    ACQUIRED = "acquired"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class RepoTarget:
    """One repository to scan, as enumerated from a host."""

    host: str
    org: str
    name: str
    default_branch: str
    clone_url: str
    archived: bool = False
    fork: bool = False
    # Set for user-supplied clones; the tool must never modify this directory.
    external_path: Path | None = None
    # Set when the repository was named explicitly but could not be resolved.
    # Carried as a target rather than dropped, so it still reaches reporting as
    # a failure instead of silently shrinking the target set.
    acquisition_error: str = ""

    @property
    def slug(self) -> str:
        return f"{self.host}/{self.org}/{self.name}"

    @property
    def key(self) -> str:
        """Stable identity for checkpointing and report layout."""
        return f"{self.host}|{self.org}|{self.name}"

    @property
    def is_external(self) -> bool:
        return self.external_path is not None


@dataclass
class AcquisitionResult:
    """The outcome of acquiring one repository, and where to read it."""

    target: RepoTarget
    outcome: AcquisitionOutcome
    path: Path | None = None
    commit_sha: str | None = None
    branch: str | None = None
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.outcome is AcquisitionOutcome.ACQUIRED and self.path is not None
