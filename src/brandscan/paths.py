"""Output-directory layout, namespaced by host / organisation / repository.

Repository names collide freely across organisations and across the two hosts,
so every artifact path is qualified by all three segments. Nothing is ever
written to a path derived from the repository name alone.

The tree has two levels. The *output root* holds what is shared between runs —
the clone tree — and one directory per run. A *run directory* holds everything
that is evidence of one particular run: its reports, its executive summary, its
checkpoint, its log and its record. A completed run is therefore never
overwritten by the next one, which is what makes two runs comparable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from brandscan.run_record import RunRecord

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

RUN_DIR_SUFFIX = "-run"

RUN_RECORD_NAME = "run.json"

# `2026-07-31-142530-run`, and `…-run-2` for the second run of one second.
RUN_DIR_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{6}" + RUN_DIR_SUFFIX + r"(-\d+)?$")

# Far beyond any plausible number of runs starting in the same second; the loop
# is bounded so a directory that cannot be created fails loudly.
MAX_RUN_DIR_ATTEMPTS = 1000


def safe_segment(value: str) -> str:
    """Reduce a host / org / repo name to a safe single path segment.

    Hosts carry dots and repositories occasionally carry characters that are
    illegal on Windows paths. Collapsing them keeps the layout portable while
    the three-segment nesting keeps it unambiguous.
    """
    cleaned = _UNSAFE.sub("-", value.strip()).strip("-.")
    return cleaned or "unnamed"


def run_id_for(started_at: datetime) -> str:
    """The directory name for a run starting at a given instant.

    UTC, deliberately. Every other instant the tool records is UTC, so a name in
    local time would be the one timestamp in the tree that could not be lined up
    against the others — and local time is not monotonic, so at the autumn
    daylight-saving fold an hour of names repeats.
    """
    moment = started_at.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%d-%H%M%S") + RUN_DIR_SUFFIX


def create_run_dir(root: Path, started_at: datetime | None = None) -> Path:
    """Claim a new run directory under an output root.

    The directory is created here rather than merely named, so that two runs
    starting in the same second cannot both decide the name is free.
    """
    base = run_id_for(started_at or datetime.now(timezone.utc))
    for attempt in range(MAX_RUN_DIR_ATTEMPTS):
        name = base if attempt == 0 else f"{base}-{attempt + 1}"
        candidate = root / name
        try:
            candidate.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return candidate
    raise OSError(f"could not claim a run directory under {root}")


def discover_runs(root: Path) -> list[tuple[Path, RunRecord | None]]:
    """Every run directory under an output root, most recent first.

    Names sort chronologically, so ordering by name reversed is ordering by
    recency without reading anything. A directory whose record is missing or
    unreadable is still listed, carrying `None` — a truncated record from a hard
    kill must not make the run invisible, still less end the next one.
    """
    if not root.is_dir():
        return []
    runs: list[tuple[Path, RunRecord | None]] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name, reverse=True):
        if not child.is_dir() or not RUN_DIR_NAME.match(child.name):
            continue
        runs.append((child, RunRecord.load(child / RUN_RECORD_NAME)))
    return runs


@dataclass(frozen=True)
class OutputLayout:
    """Every path the run writes to, derived from the output root and its run.

    `root` is shared between runs and holds the clones; `run_dir` belongs to
    this run alone and holds everything else.
    """

    root: Path
    run_dir: Path

    @property
    def run_id(self) -> str:
        return self.run_dir.name

    @property
    def reports_dir(self) -> Path:
        return self.run_dir / "reports"

    @property
    def clones_dir(self) -> Path:
        """Where managed clones live. Only this tree is ever hard-reset.

        Shared across runs and outside every run directory: a clone is a working
        copy, not evidence. What a run saw in one is recorded in that run's
        reports, pinned to the commit it scanned.
        """
        return self.root / "clones"

    @property
    def checkpoint_file(self) -> Path:
        return self.run_dir / "checkpoint.json"

    @property
    def log_file(self) -> Path:
        return self.run_dir / "run.log.jsonl"

    @property
    def run_record_file(self) -> Path:
        return self.run_dir / RUN_RECORD_NAME

    @property
    def summary_file(self) -> Path:
        return self.run_dir / "executive-summary.md"

    @property
    def summary_json_file(self) -> Path:
        return self.run_dir / "executive-summary.json"

    @property
    def summary_html_file(self) -> Path:
        """The browsable form. Always written, so no run is missing it."""
        return self.run_dir / "executive-summary.html"

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
        """Path to a repo report as written in the executive summary.

        Relative to the run directory the summary itself sits in, so a summary
        never links into another run's reports.
        """
        target = self.report_markdown(host, org, name).relative_to(self.run_dir)
        return target.as_posix()

    def bootstrap(self) -> None:
        """Create the directory skeleton for a run."""
        for directory in (self.root, self.run_dir, self.reports_dir, self.clones_dir):
            directory.mkdir(parents=True, exist_ok=True)


def select_layout(
    root: Path,
    run_id: str | None = None,
    force_new: bool = False,
    now: datetime | None = None,
) -> OutputLayout:
    """Decide which run directory this invocation writes to.

    An explicitly named run wins outright, whether or not it finished. Failing
    that, a run asked to scan everything again gets a directory of its own,
    because its results are a new run's rather than an amendment to an old one.
    Otherwise the most recent unfinished run is continued — so the promise that
    re-running the same command resumes an interrupted run holds without the
    operator having to have noted a directory name — and a new run is started
    when the most recent one finished or none exists.
    """
    if run_id:
        return OutputLayout(root=root, run_dir=root / run_id)
    if not force_new:
        for run_dir, record in discover_runs(root):
            # A run whose record did not survive says nothing either way, so it
            # is passed over rather than resumed or treated as a failure.
            if record is None:
                continue
            if not record.is_finished:
                return OutputLayout(root=root, run_dir=run_dir)
            # The most recent run that did record its state finished, so this
            # invocation is a new run rather than a continuation of it.
            break
    return OutputLayout(root=root, run_dir=create_run_dir(root, now))
