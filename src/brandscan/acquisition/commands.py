"""Thin wrappers over the `gh` and `git` executables.

Kept in one place so that every external invocation is timed out, captured, and
surfaced as a typed error rather than a raw `CalledProcessError` somewhere deep
in the run.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

DEFAULT_TIMEOUT = 600


class CommandError(Exception):
    """A subprocess that failed, with its stderr attached for reporting."""

    def __init__(self, argv: Sequence[str], returncode: int, stderr: str) -> None:
        self.argv = list(argv)
        self.returncode = returncode
        self.stderr = stderr.strip()
        super().__init__(
            f"{' '.join(self.argv[:3])} failed with exit code {returncode}: {self.stderr}"
        )


@dataclass(frozen=True)
class CompletedCommand:
    stdout: str
    stderr: str


def run(
    argv: Sequence[str], cwd: Path | None = None, timeout: int = DEFAULT_TIMEOUT
) -> CompletedCommand:
    """Run a command, raising `CommandError` on a non-zero exit."""
    try:
        completed = subprocess.run(
            list(argv),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CommandError(argv, 127, f"executable not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandError(argv, 124, f"timed out after {timeout}s") from exc

    if completed.returncode != 0:
        raise CommandError(argv, completed.returncode, completed.stderr or completed.stdout)
    return CompletedCommand(stdout=completed.stdout, stderr=completed.stderr)


def executable_available(name: str) -> bool:
    return shutil.which(name) is not None


# --- gh -------------------------------------------------------------------


def gh(args: Sequence[str], timeout: int = DEFAULT_TIMEOUT) -> CompletedCommand:
    return run(["gh", *args], timeout=timeout)


def gh_api_json(host: str, endpoint: str, paginate: bool = False) -> Any:
    """Call a REST endpoint on a specific host and parse the JSON response.

    `--paginate` is what keeps enumeration complete; without it an organisation
    larger than one page silently reports a truncated repository list.
    """
    args = ["api", "--hostname", host]
    if paginate:
        args += ["--paginate", "--slurp"]
    args.append(endpoint)
    result = gh(args)
    text = result.stdout.strip()
    if not text:
        return []
    payload = json.loads(text)
    if paginate and isinstance(payload, list):
        # --slurp yields one array per page; flatten to a single sequence.
        flattened: list[Any] = []
        for page in payload:
            if isinstance(page, list):
                flattened.extend(page)
            else:
                flattened.append(page)
        return flattened
    return payload


# --- git ------------------------------------------------------------------


def git(args: Sequence[str], cwd: Path | None = None, timeout: int = DEFAULT_TIMEOUT) -> str:
    return run(["git", *args], cwd=cwd, timeout=timeout).stdout.strip()


def git_head_sha(repo_dir: Path) -> str:
    return git(["rev-parse", "HEAD"], cwd=repo_dir)


def git_current_branch(repo_dir: Path) -> str:
    return git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)


def git_origin_url(repo_dir: Path) -> str:
    """The origin remote as *configured*, for identity comparison.

    Read via `config --get` rather than `remote get-url`, because the latter
    applies any `url.<base>.insteadOf` rewrites. A site that mirrors github.com
    through an internal host would then report every clone's origin as the
    mirror, and the origin guard would reject every repository it checked.
    """
    return git(["config", "--get", "remote.origin.url"], cwd=repo_dir)


def git_is_dirty(repo_dir: Path) -> bool:
    """True when the working tree has uncommitted or untracked changes."""
    return bool(git(["status", "--porcelain"], cwd=repo_dir))
