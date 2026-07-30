"""Acquisition: the origin guard, the two safety postures, and resumability."""

from __future__ import annotations

from pathlib import Path

import pytest

from brandscan.acquisition.checkpoint import Checkpoint
from brandscan.acquisition.clone import (
    acquire_external,
    acquire_managed,
    normalise_remote,
    remotes_match,
)
from brandscan.acquisition.enumerate_repos import filter_repos
from brandscan.acquisition.models import AcquisitionOutcome, RepoTarget
from brandscan.config.model import Target
from tests.conftest import git, make_git_repo

HTTPS = "https://github.com/contoso/widgets.git"


def target(**overrides) -> RepoTarget:
    defaults = dict(
        host="github.com",
        org="contoso",
        name="widgets",
        default_branch="master",
        clone_url=HTTPS,
    )
    return RepoTarget(**{**defaults, **overrides})


# --- Remote identity ------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/contoso/widgets.git",
        "https://github.com/contoso/widgets",
        "https://token@github.com/Contoso/Widgets.git",
        "git@github.com:contoso/widgets.git",
        "ssh://git@github.com/contoso/widgets",
        "https://github.com/contoso/widgets/",
    ],
)
def test_equivalent_remote_spellings_all_match(url: str):
    assert remotes_match(url, "github.com", "contoso", "widgets")


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/contoso/gadgets.git",
        "https://github.enterprise.example/contoso/widgets.git",
        "https://github.com/fabrikam/widgets.git",
        "",
    ],
)
def test_a_different_repository_does_not_match(url: str):
    assert not remotes_match(url, "github.com", "contoso", "widgets")


def test_unparseable_remote_is_not_treated_as_a_match():
    assert normalise_remote("not a url at all") is None or not remotes_match(
        "not a url at all", "github.com", "contoso", "widgets"
    )


# --- Managed clones -------------------------------------------------------


def publish(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    """A bare repository standing in for the remote."""
    source = make_git_repo(tmp_path / "source", HTTPS, files)
    bare = tmp_path / "remote.git"
    git(["clone", "--bare", str(source), str(bare)], cwd=tmp_path)
    return bare


def point_at(clone: Path, bare: Path) -> None:
    """Give a managed clone a real-looking origin that still resolves locally."""
    file_url = bare.as_uri()
    git(["remote", "set-url", "origin", HTTPS], cwd=clone)
    git(["config", f"url.{file_url}.insteadOf", HTTPS], cwd=clone)


def test_first_acquisition_records_the_commit(tmp_path: Path):
    bare = publish(tmp_path, {"README.md": "Contoso\n"})
    destination = tmp_path / "managed" / "widgets"

    result = acquire_managed(target(clone_url=bare.as_uri()), destination)

    assert result.outcome is AcquisitionOutcome.ACQUIRED
    assert result.branch == "master"
    assert result.commit_sha and len(result.commit_sha) == 40
    assert (destination / "README.md").read_text(encoding="utf-8") == "Contoso\n"


def test_re_run_updates_to_the_current_tip_and_discards_local_divergence(tmp_path: Path):
    bare = publish(tmp_path, {"README.md": "first\n"})
    destination = tmp_path / "managed" / "widgets"
    acquire_managed(target(clone_url=bare.as_uri()), destination)
    point_at(destination, bare)

    # The remote advances.
    publisher = tmp_path / "publisher"
    git(["clone", str(bare), str(publisher)], cwd=tmp_path)
    git(["config", "user.email", "t@example.invalid"], cwd=publisher)
    git(["config", "user.name", "t"], cwd=publisher)
    (publisher / "README.md").write_text("second\n", encoding="utf-8")
    git(["commit", "-am", "advance"], cwd=publisher)
    git(["push", "origin", "master"], cwd=publisher)

    # And the managed clone has been messed with locally.
    (destination / "README.md").write_text("local edit\n", encoding="utf-8")
    (destination / "stray.txt").write_text("untracked\n", encoding="utf-8")

    result = acquire_managed(target(), destination)

    assert result.outcome is AcquisitionOutcome.ACQUIRED
    assert (destination / "README.md").read_text(encoding="utf-8") == "second\n"
    assert not (destination / "stray.txt").exists()


def test_a_managed_directory_for_another_repository_fails_and_is_left_alone(tmp_path: Path):
    intruder = make_git_repo(
        tmp_path / "managed" / "widgets",
        "https://github.com/fabrikam/something-else.git",
        {"KEEP.txt": "do not touch\n"},
    )

    result = acquire_managed(target(), intruder)

    assert result.outcome is AcquisitionOutcome.FAILED
    assert "not github.com/contoso/widgets" in result.reason
    assert (intruder / "KEEP.txt").read_text(encoding="utf-8") == "do not touch\n"


def test_a_non_repository_directory_in_the_way_is_not_overwritten(tmp_path: Path):
    destination = tmp_path / "managed" / "widgets"
    destination.mkdir(parents=True)
    (destination / "important.txt").write_text("mine\n", encoding="utf-8")

    result = acquire_managed(target(), destination)

    assert result.outcome is AcquisitionOutcome.FAILED
    assert (destination / "important.txt").exists()


# --- External clones ------------------------------------------------------


def test_clean_external_clone_is_scanned_in_place(tmp_path: Path):
    external = make_git_repo(tmp_path / "work" / "widgets", HTTPS, {"a.txt": "Contoso\n"})
    result = acquire_external(target(external_path=external))

    assert result.outcome is AcquisitionOutcome.ACQUIRED
    assert result.path == external
    assert result.commit_sha and len(result.commit_sha) == 40
    assert result.branch == "master"


def test_dirty_external_clone_is_skipped_and_left_untouched(tmp_path: Path):
    external = make_git_repo(tmp_path / "work" / "widgets", HTTPS, {"a.txt": "committed\n"})
    (external / "a.txt").write_text("uncommitted work\n", encoding="utf-8")
    (external / "scratch.md").write_text("notes\n", encoding="utf-8")
    before = git(["rev-parse", "HEAD"], cwd=external)

    result = acquire_external(target(external_path=external))

    assert result.outcome is AcquisitionOutcome.SKIPPED
    assert "uncommitted" in result.reason
    # Nothing about the working copy moved.
    assert (external / "a.txt").read_text(encoding="utf-8") == "uncommitted work\n"
    assert (external / "scratch.md").read_text(encoding="utf-8") == "notes\n"
    assert git(["rev-parse", "HEAD"], cwd=external) == before
    assert git(["status", "--porcelain"], cwd=external)


def test_external_path_that_is_not_a_repository_fails(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    result = acquire_external(target(external_path=plain))
    assert result.outcome is AcquisitionOutcome.FAILED


def test_missing_external_path_fails(tmp_path: Path):
    result = acquire_external(target(external_path=tmp_path / "absent"))
    assert result.outcome is AcquisitionOutcome.FAILED


# --- Enumeration filters --------------------------------------------------


def repo(**overrides) -> RepoTarget:
    return target(**{"default_branch": "main", **overrides})


def test_archived_and_forked_repositories_are_excluded_by_default():
    repos = [
        repo(name="live"),
        repo(name="old", archived=True),
        repo(name="copy", fork=True),
    ]
    kept = filter_repos(repos, Target(host="github.com", org="contoso"))
    assert {r.name for r in kept} == {"live"}


def test_archived_repositories_can_be_included():
    repos = [repo(name="live"), repo(name="old", archived=True)]
    kept = filter_repos(
        repos, Target(host="github.com", org="contoso", include_archived=True)
    )
    assert {r.name for r in kept} == {"live", "old"}


def test_a_repository_without_a_default_branch_is_dropped_as_empty():
    kept = filter_repos(
        [repo(name="empty", default_branch="")], Target(host="github.com", org="contoso")
    )
    assert kept == []


def test_a_non_main_default_branch_is_carried_through():
    kept = filter_repos(
        [repo(name="legacy", default_branch="trunk")],
        Target(host="github.com", org="contoso"),
    )
    assert kept[0].default_branch == "trunk"


# --- Checkpointing --------------------------------------------------------


def test_checkpoint_round_trips(tmp_path: Path):
    path = tmp_path / "checkpoint.json"
    checkpoint = Checkpoint.load(path)
    assert not checkpoint.is_complete("github.com|contoso|widgets")

    checkpoint.record("github.com|contoso|widgets", {"status": "clean"})
    reloaded = Checkpoint.load(path)
    assert reloaded.is_complete("github.com|contoso|widgets")
    assert reloaded.entry("github.com|contoso|widgets")["status"] == "clean"


def test_a_corrupt_checkpoint_starts_clean_rather_than_crashing(tmp_path: Path):
    path = tmp_path / "checkpoint.json"
    path.write_text('{"version": 1, "repositories": {"a"', encoding="utf-8")
    assert Checkpoint.load(path).entries == {}


def test_clearing_a_checkpoint_forgets_everything(tmp_path: Path):
    path = tmp_path / "checkpoint.json"
    checkpoint = Checkpoint.load(path)
    checkpoint.record("k", {"status": "clean"})
    checkpoint.clear()
    assert Checkpoint.load(path).entries == {}
