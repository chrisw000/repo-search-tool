"""Enumerating the target set across hosts and organisations.

Two properties matter here and both are easy to get silently wrong:
completeness (an organisation larger than one result page must not be
truncated) and the default branch (legacy repositories default to `master`,
`develop`, or `trunk`, and those are precisely the repositories most likely to
carry stale branding).
"""

from __future__ import annotations

from pathlib import Path

from brandscan.acquisition.commands import CommandError, gh_api_json
from brandscan.acquisition.models import RepoTarget
from brandscan.config.model import Config, ExternalRepo, Target
from brandscan.logging_setup import info, warning

PAGE_SIZE = 100


class EnumerationError(Exception):
    """One organisation could not be enumerated. Does not end the run."""


def _repo_from_api(host: str, org: str, payload: dict) -> RepoTarget:
    # The API's own `default_branch` is the only trustworthy source. Never
    # assume `main`: guessing produces an empty scan rather than an error,
    # which is the worst possible failure mode for this tool.
    default_branch = payload.get("default_branch") or ""
    return RepoTarget(
        host=host,
        org=org,
        name=str(payload.get("name", "")),
        default_branch=default_branch,
        clone_url=str(payload.get("clone_url") or payload.get("ssh_url") or ""),
        archived=bool(payload.get("archived", False)),
        fork=bool(payload.get("fork", False)),
    )


def enumerate_org(target: Target) -> list[RepoTarget]:
    """List every repository in one organisation, across all result pages."""
    endpoint = f"orgs/{target.org}/repos?per_page={PAGE_SIZE}&type=all&sort=full_name"
    try:
        payloads = gh_api_json(target.host, endpoint, paginate=True)
    except CommandError as exc:
        raise EnumerationError(
            f"could not enumerate {target.label}: {exc.stderr or exc}"
        ) from exc

    repos: list[RepoTarget] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        repo = _repo_from_api(target.host, target.org, payload)
        if not repo.name:
            continue
        repos.append(repo)
    return repos


def filter_repos(repos: list[RepoTarget], target: Target) -> list[RepoTarget]:
    """Apply the archived and fork inclusion flags, both off by default."""
    kept: list[RepoTarget] = []
    excluded_archived = 0
    excluded_forks = 0
    for repo in repos:
        if repo.archived and not target.include_archived:
            excluded_archived += 1
            continue
        if repo.fork and not target.include_forks:
            excluded_forks += 1
            continue
        if not repo.default_branch:
            # An empty repository has no default branch and nothing to scan.
            warning(
                "repository has no default branch; skipping as empty",
                repository=repo.slug,
            )
            continue
        kept.append(repo)

    info(
        "organisation enumerated",
        host=target.host,
        org=target.org,
        found=len(repos),
        targeted=len(kept),
        excluded_archived=excluded_archived,
        excluded_forks=excluded_forks,
    )
    return kept


def _external_target(external: ExternalRepo) -> RepoTarget:
    """Build a target for a user-supplied directory.

    The branch and clone URL are read from the directory itself at acquisition
    time; nothing here contacts a host, because an external clone is scanned
    exactly as it stands.
    """
    return RepoTarget(
        host=external.host,
        org=external.org,
        name=external.name,
        default_branch="",
        clone_url="",
        external_path=Path(external.path),
    )


def enumerate_targets(config: Config) -> tuple[list[RepoTarget], list[str]]:
    """Build the full target set for a run.

    Returns the targets together with any organisation-level enumeration
    errors, which are reported but do not end the run.
    """
    targets: list[RepoTarget] = []
    errors: list[str] = []

    for target in config.targets:
        try:
            repos = enumerate_org(target)
        except EnumerationError as exc:
            errors.append(str(exc))
            warning("organisation enumeration failed", org=target.label, reason=str(exc))
            continue
        targets.extend(filter_repos(repos, target))

    for external in config.external_repositories:
        targets.append(_external_target(external))

    # A repository can be reachable both by enumeration and as an external
    # clone. The external entry wins: the operator named it explicitly.
    deduped: dict[str, RepoTarget] = {}
    for repo in targets:
        if repo.key in deduped and not repo.is_external:
            continue
        deduped[repo.key] = repo

    return list(deduped.values()), errors
