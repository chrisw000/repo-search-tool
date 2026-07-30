"""The finding — the single unit both search capabilities produce.

Text matches and image matches share one shape so that reporting, ranking, and
the summary never need to know which capability produced a finding. That is
also what lets a new matching strategy reach reporting without touching it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from brandscan.config.model import Severity


class MatchType(str, Enum):
    TEXT = "text"
    IMAGE = "image"


@dataclass
class Finding:
    """One located trace of the old brand.

    `matched` names the search-group for a text match and the reference-image
    label for an image match — in both cases, what the reader needs in order to
    know *what* was found.
    """

    match_type: MatchType
    matched: str
    path: str
    severity: Severity
    line: int | None = None
    context: list[str] = field(default_factory=list)
    excerpt: str = ""
    distance: int | None = None
    remediation: str = ""
    permalink: str = ""
    # Set when an image was recovered from a base64 data URI rather than read
    # from a file of its own, so a reader can find it.
    embedded_in: str | None = None

    @property
    def sort_key(self) -> tuple[int, str, int]:
        return (-self.severity.weight, self.path, self.line or 0)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "match_type": self.match_type.value,
            "matched": self.matched,
            "path": self.path,
            "line": self.line,
            "severity": self.severity.value,
            "permalink": self.permalink,
        }
        if self.excerpt:
            payload["excerpt"] = self.excerpt
        if self.context:
            payload["context"] = self.context
        if self.distance is not None:
            payload["distance"] = self.distance
        if self.remediation:
            payload["remediation"] = self.remediation
        if self.embedded_in:
            payload["embedded_in"] = self.embedded_in
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Finding":
        return cls(
            match_type=MatchType(payload["match_type"]),
            matched=payload["matched"],
            path=payload["path"],
            severity=Severity(payload["severity"]),
            line=payload.get("line"),
            context=list(payload.get("context", [])),
            excerpt=payload.get("excerpt", ""),
            distance=payload.get("distance"),
            remediation=payload.get("remediation", ""),
            permalink=payload.get("permalink", ""),
            embedded_in=payload.get("embedded_in"),
        )


@dataclass
class ScanIssue:
    """A file the scan could not read, recorded rather than raised.

    One malformed SVG or one undecodable base64 blob must never end a
    repository's scan, but it must not vanish either — a silent skip is
    indistinguishable from a clean file.
    """

    path: str
    reason: str
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": self.path, "reason": self.reason}
        if self.line is not None:
            payload["line"] = self.line
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScanIssue":
        return cls(
            path=payload["path"], reason=payload["reason"], line=payload.get("line")
        )
