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


class UnreadableCause(str, Enum):
    """Why an input could not be read — a closed set, not free text.

    The remedies have nothing in common: a placeholder wants artwork, a pointer
    wants fetching, a corrupt file wants repairing. Reporting them all as one
    undifferentiated failure is what makes the unreadable section unactionable,
    and free text cannot be grouped or counted. The specific parser message
    still matters when the cause is `MALFORMED`, so it survives alongside this
    as the issue's `reason`.
    """

    EMPTY = "empty"
    NOT_AN_IMAGE = "not_an_image"
    VCS_POINTER = "vcs_pointer"
    MALFORMED = "malformed"
    RENDERED_BLANK = "rendered_blank"

    @property
    def heading(self) -> str:
        return _CAUSE_HEADINGS[self]

    @property
    def remediation(self) -> str:
        """What would be needed to assess this input."""
        return _CAUSE_REMEDIATION[self]


_CAUSE_HEADINGS: dict[UnreadableCause, str] = {
    UnreadableCause.EMPTY: "Empty placeholders",
    UnreadableCause.NOT_AN_IMAGE: "Not images",
    UnreadableCause.VCS_POINTER: "Content never fetched",
    UnreadableCause.MALFORMED: "Malformed or truncated images",
    UnreadableCause.RENDERED_BLANK: "Decoded to nothing",
}

_CAUSE_REMEDIATION: dict[UnreadableCause, str] = {
    UnreadableCause.EMPTY: (
        "The file holds no content — it is a placeholder somebody committed on "
        "purpose, not a defect. Nothing here can carry brand residue. If the "
        "artwork it stands in for has since arrived, supply the new-brand asset; "
        "otherwise leave it alone."
    ),
    UnreadableCause.NOT_AN_IMAGE: (
        "The file has an image extension but does not contain image data — most "
        "often an error page or a redirect saved under the image's name. Restore "
        "the real asset, then re-run to assess it."
    ),
    UnreadableCause.VCS_POINTER: (
        "The file is a version-control pointer: the real content was never "
        "fetched into this clone. Fetch the underlying objects (for Git LFS, "
        "`git lfs pull`) and re-run. Large brand assets are exactly what a "
        "repository stores this way, so treat these as high-value unknowns "
        "rather than as noise."
    ),
    UnreadableCause.MALFORMED: (
        "The image data is corrupt or truncated and no decoder could read it. "
        "Repair or replace the file from its source, then re-run to assess it. "
        "The recorded reason carries the decoder's own message."
    ),
    UnreadableCause.RENDERED_BLANK: (
        "The file decoded without error but yielded no content at all. That is "
        "usually a truncated image a lenient decoder accepted; it can also be a "
        "legitimately solid-colour swatch or spacer, which has no layout to "
        "match against and so was never assessable. Confirm which, and replace "
        "it if it should have held artwork."
    ),
}


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
    cause: UnreadableCause | None = None

    @property
    def remediation(self) -> str:
        return self.cause.remediation if self.cause else ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": self.path, "reason": self.reason}
        if self.line is not None:
            payload["line"] = self.line
        if self.cause is not None:
            payload["cause"] = self.cause.value
            payload["remediation"] = self.cause.remediation
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScanIssue":
        cause = payload.get("cause")
        return cls(
            path=payload["path"],
            reason=payload["reason"],
            line=payload.get("line"),
            cause=UnreadableCause(cause) if cause else None,
        )
