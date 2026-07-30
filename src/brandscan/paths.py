"""Output-directory layout, namespaced by host / organisation / repository.

Repository names collide freely across organisations and across the two hosts,
so every artifact path is qualified by all three segments. Nothing is ever
written to a path derived from the repository name alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_segment(value: str) -> str:
    """Reduce a host / org / repo name to a safe single path segment.

    Hosts carry dots and repositories occasionally carry characters that are
    illegal on Windows paths. Collapsing them keeps the layout portable while
    the three-segment nesting keeps it unambiguous.
    """
    cleaned = _UNSAFE.sub("-", value.strip()).strip("-.")
    return cleaned or "unnamed"


@dataclass(frozen=True)
class OutputLayout:
    """Every path the run writes to, derived from one output root."""

    root: Path

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def clones_dir(self) -> Path:
        """Where managed clones live. Only this tree is ever hard-reset."""
        return self.root / "clones"

    @property
    def checkpoint_file(self) -> Path:
        return self.root / "checkpoint.json"

    @property
    def log_file(self) -> Path:
        return self.root / "run.log.jsonl"

    @property
    def summary_file(self) -> Path:
        return self.root / "executive-summary.md"

    @property
    def summary_json_file(self) -> Path:
        return self.root / "executive-summary.json"

    def repo_dir(self, host: str, org: str, name: str) -> Path:
        return (
            self.clones_dir / safe_segment(host) / safe_segment(org) / safe_segment(name)
        )

    def report_dir(self, host: str, org: str, name: str) -> Path:
        return (
            self.reports_dir / safe_segment(host) / safe_segment(org) / safe_segment(name)
        )

    def report_markdown(self, host: str, org: str, name: str) -> Path:
        return self.report_dir(host, org, name) / "report.md"

    def report_json(self, host: str, org: str, name: str) -> Path:
        return self.report_dir(host, org, name) / "report.json"

    def summary_relative_link(self, host: str, org: str, name: str) -> str:
        """Path to a repo report as written in the executive summary."""
        target = self.report_markdown(host, org, name).relative_to(self.root)
        return target.as_posix()

    def bootstrap(self) -> None:
        """Create the directory skeleton for a run."""
        for directory in (self.root, self.reports_dir, self.clones_dir):
            directory.mkdir(parents=True, exist_ok=True)
