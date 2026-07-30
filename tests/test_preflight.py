"""Multi-host preflight and complete enumeration.

Both talk to `gh`, so the executable itself is stubbed and what is asserted is
the decision made from its answers.
"""

from __future__ import annotations

import json

import pytest

from brandscan.acquisition import commands, enumerate_repos, preflight
from brandscan.acquisition.commands import CommandError, CompletedCommand
from brandscan.acquisition.preflight import PreflightError, run_preflight
from brandscan.config.model import Target

GITHUB = Target(host="github.com", org="contoso")
ENTERPRISE = Target(host="ghes.example", org="platform")


@pytest.fixture(autouse=True)
def gh_is_installed(monkeypatch):
    monkeypatch.setattr(preflight, "executable_available", lambda name: True)


def stub_gh(monkeypatch, responses):
    """Route `gh` calls through a table keyed by a substring of the argv."""

    def fake_gh(args, timeout=commands.DEFAULT_TIMEOUT):
        joined = " ".join(args)
        for needle, outcome in responses.items():
            if needle in joined:
                if isinstance(outcome, Exception):
                    raise outcome
                return CompletedCommand(stdout=outcome, stderr="")
        return CompletedCommand(stdout="", stderr="")

    monkeypatch.setattr(preflight, "gh", fake_gh)
    monkeypatch.setattr(commands, "gh", fake_gh)


def stub_api(monkeypatch, responses):
    def fake_api(host, endpoint, paginate=False):
        for needle, outcome in responses.items():
            if needle in f"{host} {endpoint}":
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        return []

    monkeypatch.setattr(preflight, "gh_api_json", fake_api)
    monkeypatch.setattr(enumerate_repos, "gh_api_json", fake_api)


# --- Preflight ------------------------------------------------------------


def test_all_hosts_and_organisations_reachable(monkeypatch):
    stub_gh(monkeypatch, {"auth status": ""})
    stub_api(monkeypatch, {"orgs/": [{"name": "widgets"}]})

    report = run_preflight([GITHUB, ENTERPRISE])
    assert report.checked_hosts == ["github.com", "ghes.example"]
    assert report.checked_orgs == ["github.com/contoso", "ghes.example/platform"]


def test_a_host_without_a_session_aborts_and_names_its_remedy(monkeypatch):
    failure = CommandError(["gh", "auth", "status"], 1, "not logged in")
    stub_gh(monkeypatch, {"--hostname ghes.example": failure, "auth status": ""})
    stub_api(monkeypatch, {"orgs/": [{"name": "widgets"}]})

    with pytest.raises(PreflightError) as excinfo:
        run_preflight([GITHUB, ENTERPRISE])

    failures = excinfo.value.failures
    assert [f.host for f in failures] == ["ghes.example"]
    assert failures[0].org is None
    assert "gh auth login --hostname ghes.example" in failures[0].remedy


def test_a_valid_session_with_an_unauthorised_org_is_reported_distinctly(monkeypatch):
    """A token can be valid yet not SSO-authorised for an organisation."""
    stub_gh(monkeypatch, {"auth status": ""})
    stub_api(
        monkeypatch,
        {
            "github.com": [{"name": "widgets"}],
            "ghes.example": CommandError(
                ["gh", "api"], 1, "HTTP 403: SAML SSO enforcement (orgs/platform/repos)"
            ),
        },
    )

    with pytest.raises(PreflightError) as excinfo:
        run_preflight([GITHUB, ENTERPRISE])

    failure = excinfo.value.failures[0]
    assert failure.host == "ghes.example"
    assert failure.org == "platform"
    assert "authenticated session exists" in failure.reason
    assert "SSO" in failure.remedy


def test_every_failing_host_is_reported_in_one_pass(monkeypatch):
    failure = CommandError(["gh", "auth", "status"], 1, "not logged in")
    stub_gh(monkeypatch, {"auth status": failure})
    stub_api(monkeypatch, {})

    with pytest.raises(PreflightError) as excinfo:
        run_preflight([GITHUB, ENTERPRISE])
    assert {f.host for f in excinfo.value.failures} == {"github.com", "ghes.example"}


def test_a_missing_gh_binary_is_not_mistaken_for_a_session(monkeypatch):
    monkeypatch.setattr(preflight, "executable_available", lambda name: False)
    with pytest.raises(PreflightError) as excinfo:
        run_preflight([GITHUB])
    assert "gh CLI was not found" in excinfo.value.failures[0].reason


# --- Enumeration ----------------------------------------------------------


def test_enumeration_spans_every_result_page(monkeypatch):
    """`--paginate --slurp` returns one array per page; all of them count."""
    pages = [
        [{"name": f"repo-{n}", "default_branch": "main", "clone_url": "u"} for n in range(100)],
        [{"name": f"repo-{n}", "default_branch": "main", "clone_url": "u"} for n in range(100, 180)],
    ]

    def fake_gh(args, timeout=commands.DEFAULT_TIMEOUT):
        assert "--paginate" in args, "enumeration must not stop at the first page"
        return CompletedCommand(stdout=json.dumps(pages), stderr="")

    monkeypatch.setattr(commands, "gh", fake_gh)
    monkeypatch.setattr(enumerate_repos, "gh_api_json", commands.gh_api_json)

    repos = enumerate_repos.enumerate_org(GITHUB)
    assert len(repos) == 180


def test_an_unenumerable_organisation_does_not_end_the_run(monkeypatch):
    from brandscan.config.model import Config

    stub_api(
        monkeypatch,
        {
            "github.com": [
                {"name": "widgets", "default_branch": "master", "clone_url": "u"}
            ],
            "ghes.example": CommandError(["gh", "api"], 1, "HTTP 404"),
        },
    )

    config = Config(targets=[GITHUB, ENTERPRISE])
    targets, errors = enumerate_repos.enumerate_targets(config)

    assert [t.name for t in targets] == ["widgets"]
    assert len(errors) == 1
    assert "ghes.example/platform" in errors[0]


def test_the_api_default_branch_is_used_verbatim(monkeypatch):
    stub_api(
        monkeypatch,
        {
            "orgs/": [
                {"name": "legacy", "default_branch": "trunk", "clone_url": "u"},
                {"name": "modern", "default_branch": "main", "clone_url": "u"},
            ]
        },
    )
    repos = enumerate_repos.enumerate_org(GITHUB)
    assert {r.name: r.default_branch for r in repos} == {
        "legacy": "trunk",
        "modern": "main",
    }
