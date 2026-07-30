"""Multi-host authentication preflight.

Two hosts, each behind its own SSO. `gh` being installed proves nothing, and a
token can be perfectly valid yet not SSO-authorised for a given organisation.
So the preflight proves both facts per host — a session exists, *and* each
target organisation actually enumerates — and aborts before the first clone.
Discovering this on repository 200 of a multi-hour run wastes the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from brandscan.config.model import Target
from brandscan.acquisition.commands import CommandError, executable_available, gh, gh_api_json
from brandscan.logging_setup import info


@dataclass
class PreflightFailure:
    host: str
    org: str | None
    reason: str
    remedy: str

    def render(self) -> str:
        where = f"{self.host}/{self.org}" if self.org else self.host
        return f"  - {where}: {self.reason}\n      remedy: {self.remedy}"


class PreflightError(Exception):
    """Raised when any host or organisation fails the preflight."""

    def __init__(self, failures: list[PreflightFailure]) -> None:
        self.failures = failures
        body = "\n".join(failure.render() for failure in failures)
        super().__init__(
            "authentication preflight failed; no repository was acquired:\n" + body
        )


@dataclass
class PreflightReport:
    checked_hosts: list[str] = field(default_factory=list)
    checked_orgs: list[str] = field(default_factory=list)


def _check_session(host: str) -> PreflightFailure | None:
    try:
        gh(["auth", "status", "--hostname", host], timeout=60)
    except CommandError as exc:
        return PreflightFailure(
            host=host,
            org=None,
            reason=f"no authenticated session ({exc.stderr or 'gh auth status failed'})",
            remedy=f"gh auth login --hostname {host}",
        )
    return None


def _check_org(host: str, org: str) -> PreflightFailure | None:
    """Prove the organisation actually enumerates on this host.

    A session can exist while the token is not SSO-authorised for a specific
    organisation, which is why this asks for one page of repositories rather
    than trusting the session check above.
    """
    try:
        gh_api_json(host, f"orgs/{org}/repos?per_page=1")
    except CommandError as exc:
        stderr = exc.stderr.lower()
        if "sso" in stderr or "saml" in stderr:
            remedy = f"gh auth refresh --hostname {host} && authorise the token for {org} SSO"
        elif "404" in stderr or "not found" in stderr:
            remedy = (
                f"confirm the organisation name {org!r} on {host} and that your "
                "account can see it"
            )
        else:
            remedy = f"gh auth refresh --hostname {host} -s read:org,repo"
        return PreflightFailure(
            host=host,
            org=org,
            reason=(
                "authenticated session exists but the organisation could not be "
                f"enumerated ({exc.stderr or 'unknown error'})"
            ),
            remedy=remedy,
        )
    return None


def run_preflight(targets: list[Target]) -> PreflightReport:
    """Verify every host session and every organisation before acquisition.

    Collects *all* failures rather than stopping at the first, so an operator
    fixes both hosts in one pass instead of discovering the second after
    repairing the first.
    """
    report = PreflightReport()
    if not targets:
        return report

    failures: list[PreflightFailure] = []

    if not executable_available("gh"):
        raise PreflightError(
            [
                PreflightFailure(
                    host="(all)",
                    org=None,
                    reason="the gh CLI was not found on PATH",
                    remedy="install the GitHub CLI from https://cli.github.com and re-run",
                )
            ]
        )

    hosts: list[str] = []
    for target in targets:
        if target.host not in hosts:
            hosts.append(target.host)

    unusable_hosts: set[str] = set()
    for host in hosts:
        failure = _check_session(host)
        if failure:
            failures.append(failure)
            unusable_hosts.add(host)
            continue
        report.checked_hosts.append(host)
        info("host session verified", host=host)

    for target in targets:
        if target.host in unusable_hosts:
            # The session failure is the actionable problem; an org check here
            # would only restate it once per organisation.
            continue
        failure = _check_org(target.host, target.org)
        if failure:
            failures.append(failure)
            continue
        report.checked_orgs.append(target.label)
        info("organisation enumerable", host=target.host, org=target.org)

    if failures:
        raise PreflightError(failures)

    return report
