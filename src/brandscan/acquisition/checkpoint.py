"""Run checkpointing.

A run over ~400 repositories is long enough that an interruption is likely
rather than exceptional. The checkpoint is written after every repository so
that a resumed run picks up where it stopped instead of paying for the whole
run again.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brandscan.atomic import write_json_atomic

CHECKPOINT_VERSION = 1


@dataclass
class Checkpoint:
    """Per-repository completion state, persisted between runs."""

    path: Path
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Checkpoint":
        if not path.is_file():
            return cls(path=path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A truncated checkpoint from a hard kill is worth nothing but must
            # not prevent the run; start clean rather than crash.
            return cls(path=path)
        if not isinstance(data, dict) or data.get("version") != CHECKPOINT_VERSION:
            return cls(path=path)
        entries = data.get("repositories")
        return cls(path=path, entries=entries if isinstance(entries, dict) else {})

    def is_complete(self, key: str) -> bool:
        return key in self.entries

    def entry(self, key: str) -> dict[str, Any] | None:
        return self.entries.get(key)

    def record(self, key: str, payload: dict[str, Any]) -> None:
        self.entries[key] = payload
        self.save()

    def clear(self) -> None:
        self.entries.clear()
        self.save()

    def save(self) -> None:
        """Write atomically, so an interrupt cannot corrupt the checkpoint."""
        write_json_atomic(
            self.path,
            {"version": CHECKPOINT_VERSION, "repositories": self.entries},
        )
