"""What a run directory says about itself.

A run directory holds four kinds of artifact and no statement of what produced
them. The record supplies that: which run this is, when it started, what
version of the tool and which configuration produced it, and — the part the
next invocation depends on — whether the run ever finished. Without that last
fact an interrupted run is indistinguishable from a completed one, and there is
no way to decide between continuing a run and starting a new one.

It deliberately carries no finding counts and no totals. Three renderings of
the rollup already stand behind one model precisely so that they cannot
disagree; a fourth artifact restating the same figures, computed at a different
point in the run, would reintroduce exactly the drift that arrangement exists
to prevent. This record answers *which run is this*, not *what did it find* —
for that, read `executive-summary.json`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brandscan.atomic import write_json_atomic

RUN_RECORD_VERSION = 1


@dataclass
class RunRecord:
    """The identity and lifecycle of one run."""

    run_id: str
    started_at: str
    tool_version: str
    mode: str
    config_source: str | None = None
    finished_at: str | None = None

    @property
    def is_finished(self) -> bool:
        return bool(self.finished_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": RUN_RECORD_VERSION,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "tool_version": self.tool_version,
            "config_source": self.config_source,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunRecord":
        return cls(
            run_id=str(payload["run_id"]),
            started_at=str(payload["started_at"]),
            tool_version=str(payload.get("tool_version", "")),
            mode=str(payload.get("mode", "")),
            config_source=payload.get("config_source"),
            finished_at=payload.get("finished_at"),
        )

    @classmethod
    def load(cls, path: Path) -> "RunRecord | None":
        """Read a record, treating anything unreadable as absent.

        A missing, truncated or unrecognised record must not end the invocation
        that reads it: the worst it should cost is a run that could have been
        resumed being started afresh.
        """
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(payload, dict) or payload.get("version") != RUN_RECORD_VERSION:
            return None
        try:
            return cls.from_dict(payload)
        except (KeyError, ValueError):
            return None

    def write(self, path: Path) -> None:
        write_json_atomic(path, self.to_dict())
