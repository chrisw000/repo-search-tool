"""Getting a scannable copy on disk.

Two directories, two safety postures. The tool's own managed clones are reset
freely, because nobody works in them and a scan must reflect current HEAD. A
user-supplied directory is never written to at all — silently hard-resetting
over somebody's uncommitted work is not a trade-off worth any amount of
coverage, so a dirty external clone is skipped instead.
"""

from __future__ import annotations

import re
from pathlib import Path

from brandscan.acquisition.commands import (
    CommandError,
    git,
    git_current_branch,
    git_head_sha,
    git_is_dirty,
    git_origin_url,
)
from brandscan.acquisition.models import AcquisitionOutcome, AcquisitionResult, RepoTarget
from brandscan.logging_setup import debug, info, warning

_SSH_URL = re.compile(r"^(?:ssh://)?(?:[^@/]+@)?([^:/]+)[:/](.+?)(?:\.git)?/?$")
_HTTP_URL = re.compile(r"^https?://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?$")


def normalise_remote(url: str) -> tuple[str, str] | None:
    """Reduce a remote URL to `(host, owner/name)` for comparison.

    The same repository is addressed as `https://host/org/repo.git`,
    `git@host:org/repo`, and with an embedded credential. All must compare
    equal, or the origin guard would reject directories it should accept.
    """
    url = url.strip()
    if not url:
        return None
    match = _HTTP_URL.match(url) or _SSH_URL.match(url)
    if not match:
        return None
    host = match.group(1).lower()
    # Ports carry no identity for this comparison.
    host = host.split(":", 1)[0]
    path = match.group(2).lower().strip("/")
    return host, path


def remotes_match(actual: str, expected_host: str, expected_org: str, expected_name: str) -> bool:
    normalised = normalise_remote(actual)
    if normalised is None:
        return False
    host, path = normalised
    expected_path = f"{expected_org}/{expected_name}".lower()
    return host == expected_host.lower() and path == expected_path


def _is_git_repo(directory: Path) -> bool:
    return (directory / ".git").exists()


def acquire_managed(target: RepoTarget, destination: Path) -> AcquisitionResult:
    """Clone or refresh a managed shallow copy of the default branch.

    Only the default-branch tip is fetched — no history — because a rebrand
    cares about what is there now.
    """
    if _is_git_repo(destination):
        return _refresh_managed(target, destination)

    if destination.exists() and any(destination.iterdir()):
        return AcquisitionResult(
            target=target,
            outcome=AcquisitionOutcome.FAILED,
            reason=(
                f"managed directory {destination} already exists and is not a git "
                "repository; refusing to overwrite it"
            ),
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        git(
            [
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--branch",
                target.default_branch,
                target.clone_url,
                str(destination),
            ]
        )
    except CommandError as exc:
        return AcquisitionResult(
            target=target,
            outcome=AcquisitionOutcome.FAILED,
            reason=f"clone failed: {exc.stderr or exc}",
        )

    sha = git_head_sha(destination)
    info(
        "repository cloned",
        repository=target.slug,
        branch=target.default_branch,
        commit=sha[:12],
    )
    return AcquisitionResult(
        target=target,
        outcome=AcquisitionOutcome.ACQUIRED,
        path=destination,
        commit_sha=sha,
        branch=target.default_branch,
    )


def _refresh_managed(target: RepoTarget, destination: Path) -> AcquisitionResult:
    """Bring an existing managed clone to the current default-branch tip.

    Guarded first: a managed directory that does not correspond to the intended
    repository is an acquisition failure, never something to reset. Resetting
    it would destroy whatever is actually there on the strength of a path
    collision.
    """
    try:
        origin = git_origin_url(destination)
    except CommandError as exc:
        return AcquisitionResult(
            target=target,
            outcome=AcquisitionOutcome.FAILED,
            reason=f"could not read the origin remote of {destination}: {exc.stderr or exc}",
        )

    if not remotes_match(origin, target.host, target.org, target.name):
        return AcquisitionResult(
            target=target,
            outcome=AcquisitionOutcome.FAILED,
            reason=(
                f"managed directory {destination} has origin {origin!r}, which is not "
                f"{target.slug}; left untouched"
            ),
        )

    try:
        git(["fetch", "--depth", "1", "origin", target.default_branch], cwd=destination)
        git(["reset", "--hard", "FETCH_HEAD"], cwd=destination)
        git(["clean", "-fdx"], cwd=destination)
    except CommandError as exc:
        return AcquisitionResult(
            target=target,
            outcome=AcquisitionOutcome.FAILED,
            reason=f"refresh failed: {exc.stderr or exc}",
        )

    sha = git_head_sha(destination)
    debug(
        "managed clone refreshed",
        repository=target.slug,
        branch=target.default_branch,
        commit=sha[:12],
    )
    return AcquisitionResult(
        target=target,
        outcome=AcquisitionOutcome.ACQUIRED,
        path=destination,
        commit_sha=sha,
        branch=target.default_branch,
    )


def acquire_external(target: RepoTarget) -> AcquisitionResult:
    """Inspect a user-supplied clone without modifying it in any way.

    Every command here is read-only. A clean copy is scanned exactly as it
    stands, with its commit recorded so staleness is visible in the report; a
    dirty copy is skipped with the reason, never reset.
    """
    directory = target.external_path
    assert directory is not None

    if not directory.is_dir():
        return AcquisitionResult(
            target=target,
            outcome=AcquisitionOutcome.FAILED,
            reason=f"external directory not found: {directory}",
        )
    if not _is_git_repo(directory):
        return AcquisitionResult(
            target=target,
            outcome=AcquisitionOutcome.FAILED,
            reason=f"external directory is not a git repository: {directory}",
        )

    try:
        dirty = git_is_dirty(directory)
    except CommandError as exc:
        return AcquisitionResult(
            target=target,
            outcome=AcquisitionOutcome.FAILED,
            reason=f"could not read the state of {directory}: {exc.stderr or exc}",
        )

    if dirty:
        warning(
            "external clone has uncommitted changes; skipping without modifying it",
            repository=target.slug,
            path=str(directory),
        )
        return AcquisitionResult(
            target=target,
            outcome=AcquisitionOutcome.SKIPPED,
            path=directory,
            reason=(
                "external clone has uncommitted modifications; skipped rather than "
                "reset, so no local work was touched. Commit or stash the changes "
                "and re-run to include this repository."
            ),
        )

    try:
        sha = git_head_sha(directory)
        branch = git_current_branch(directory)
    except CommandError as exc:
        return AcquisitionResult(
            target=target,
            outcome=AcquisitionOutcome.FAILED,
            reason=f"could not read the checked-out commit of {directory}: {exc.stderr or exc}",
        )

    info(
        "external clone scanned in place",
        repository=target.slug,
        branch=branch,
        commit=sha[:12],
    )
    return AcquisitionResult(
        target=target,
        outcome=AcquisitionOutcome.ACQUIRED,
        path=directory,
        commit_sha=sha,
        branch=branch,
    )


def acquire(target: RepoTarget, managed_destination: Path) -> AcquisitionResult:
    """Acquire one repository by whichever posture its source implies."""
    if target.is_external:
        return acquire_external(target)
    return acquire_managed(target, managed_destination)
