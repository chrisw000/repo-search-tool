"""File-scope resolution.

Two layers of scope compose: the global one from configuration, and each
search-group's own include and exclude globs. A group narrowing its own scope
must not narrow anybody else's, so the walk enumerates once against the global
scope and each group filters that set for itself.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator

from brandscan.config.model import ScanScope, SearchGroup


def matches_any(relative_path: str, patterns: Iterable[str]) -> bool:
    """Match a repo-relative POSIX path against glob patterns.

    A bare pattern such as `*.css` is matched against the basename as well as
    the full path, because that is what a reader writing it in config means.
    """
    name = PurePosixPath(relative_path).name
    for pattern in patterns:
        if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(name, pattern):
            return True
        # `dist/**` should also match `dist/app.js` on implementations where
        # fnmatch does not treat `**` specially.
        if pattern.endswith("/**") and relative_path.startswith(pattern[:-3] + "/"):
            return True
    return False


@dataclass
class FileWalker:
    """Enumerates the in-scope files of one repository."""

    root: Path
    scope: ScanScope

    def _pruned(self, dirnames: list[str]) -> list[str]:
        excluded = set(self.scope.exclude_dirs)
        return [name for name in dirnames if name not in excluded]

    def iter_files(self) -> Iterator[Path]:
        """Yield every file passing the global scope, deepest scope first.

        Directory pruning happens during the walk rather than after it, so an
        excluded dependency tree is never descended into at all.
        """
        import os

        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(self._pruned(dirnames))
            for filename in sorted(filenames):
                path = Path(dirpath) / filename
                relative = self.relative(path)
                if matches_any(relative, self.scope.exclude_globs):
                    continue
                if self.scope.include_globs and not matches_any(
                    relative, self.scope.include_globs
                ):
                    continue
                yield path

    def relative(self, path: Path) -> str:
        return PurePosixPath(path.relative_to(self.root).as_posix()).as_posix()


def iter_files(root: Path, scope: ScanScope) -> list[Path]:
    return list(FileWalker(root=root, scope=scope).iter_files())


def group_covers(group: SearchGroup, relative_path: str) -> bool:
    """Whether one search-group's own scope admits a file.

    A group with no include globs inherits the global scope; a group that
    declares them is evaluated only against files matching them.
    """
    if matches_any(relative_path, group.exclude):
        return False
    if group.include and not matches_any(relative_path, group.include):
        return False
    return True
