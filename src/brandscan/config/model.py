"""The configuration contract.

Configuration is the extension point: a new class of brand reference is added
by editing config, never by editing code. That is why text search is modelled
as named search-groups carrying their own patterns, scope, and severity rather
than as fixed built-in categories.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# Perceptual-hash distance below which a candidate counts as the same layout.
# Empirical: tighten toward 5 to cut noise, loosen to catch more. Settled on
# the validation set; the value actually used is recorded in every report.
DEFAULT_SIMILARITY_THRESHOLD = 10


class Severity(str, Enum):
    """How much remediation work a finding implies.

    Ordered, because the executive summary ranks repositories by severity
    ahead of raw count.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def weight(self) -> int:
        return _SEVERITY_WEIGHTS[self]

    @classmethod
    def ordered(cls) -> list["Severity"]:
        return [cls.HIGH, cls.MEDIUM, cls.LOW]


# A single high-severity finding outweighs any plausible pile of low-severity
# ones, which is what makes the summary a triage order rather than a leaderboard.
_SEVERITY_WEIGHTS = {
    Severity.HIGH: 100,
    Severity.MEDIUM: 10,
    Severity.LOW: 1,
}


@dataclass(frozen=True)
class Target:
    """One `{host, organisation}` pair to enumerate."""

    host: str
    org: str
    include_archived: bool = False
    include_forks: bool = False

    @property
    def label(self) -> str:
        return f"{self.host}/{self.org}"


@dataclass(frozen=True)
class ExternalRepo:
    """A user-supplied, pre-existing local clone. Never modified by the tool."""

    host: str
    org: str
    name: str
    path: Path


@dataclass
class SearchGroup:
    """A named class of text match: patterns + scope + severity.

    Adding one is a configuration edit. The engine treats every group
    identically, so a user-defined group behaves exactly like a seeded one.
    """

    name: str
    patterns: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    severity: Severity = Severity.MEDIUM
    description: str = ""
    remediation: str = ""
    case_sensitive: bool = False

    def compiled_patterns(self) -> list[re.Pattern[str]]:
        """All patterns for this group, including those expanded from colours."""
        flags = 0 if self.case_sensitive else re.IGNORECASE
        sources = list(self.patterns)
        for colour in self.colors:
            sources.extend(colour_notation_patterns(colour))
        return [re.compile(p, flags) for p in sources]


@dataclass(frozen=True)
class ReferenceImage:
    """A reference logo and the brand layout it represents.

    Because hashing is done on luminance, the set needs one entry per distinct
    layout (horizontal, stacked, icon, wordmark) rather than one per colourway.
    """

    path: Path
    label: str


@dataclass
class ScanScope:
    """Global file scope, overridable in full by configuration.

    Dependency directories are excluded because they are third-party noise.
    Build output is deliberately *not* excluded: deployed brand assets
    frequently exist only there, and excluding it would turn the most
    shipped-facing assets into silent misses.
    """

    exclude_dirs: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)
    include_globs: list[str] = field(default_factory=list)
    max_file_bytes: int = 5 * 1024 * 1024


@dataclass
class Config:
    """A whole scan definition, validated before any repository is acquired."""

    targets: list[Target] = field(default_factory=list)
    external_repositories: list[ExternalRepo] = field(default_factory=list)
    search_groups: list[SearchGroup] = field(default_factory=list)
    reference_images: list[ReferenceImage] = field(default_factory=list)
    reference_dir: Path | None = None
    similarity_threshold: int = DEFAULT_SIMILARITY_THRESHOLD
    threshold_was_defaulted: bool = True
    scope: ScanScope = field(default_factory=ScanScope)
    output_dir: Path = Path("brandscan-output")
    source_path: Path | None = None

    def group(self, name: str) -> SearchGroup | None:
        return next((g for g in self.search_groups if g.name == name), None)

    @property
    def reference_labels(self) -> list[str]:
        """Distinct layout labels searched for, in stable order."""
        seen: list[str] = []
        for reference in self.reference_images:
            if reference.label not in seen:
                seen.append(reference.label)
        return seen


_HEX_COLOUR = re.compile(r"^#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def parse_hex_colour(value: str) -> tuple[int, int, int]:
    """Parse `#rgb` or `#rrggbb` into channel values."""
    digits = value.lstrip("#")
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def is_hex_colour(value: str) -> bool:
    return bool(_HEX_COLOUR.match(value.strip()))


def colour_notation_patterns(value: str) -> list[str]:
    """Expand one brand colour into patterns for its equivalent notations.

    The same colour is written as `#0F62FE`, as `rgb(15, 98, 254)`, and in the
    modern space-separated form. Matching only the hexadecimal spelling would
    miss the others, so every notation of a configured colour is searched for.
    """
    red, green, blue = parse_hex_colour(value)
    digits = f"{red:02x}{green:02x}{blue:02x}"

    patterns = [rf"#{digits}\b"]

    # Shorthand only exists when each channel is a repeated digit pair.
    if all(digits[i] == digits[i + 1] for i in (0, 2, 4)):
        patterns.append(rf"#{digits[0]}{digits[2]}{digits[4]}\b")

    sep = r"\s*,\s*"
    space = r"\s+"
    channels = rf"{red}{sep}{green}{sep}{blue}"
    channels_spaced = rf"{red}{space}{green}{space}{blue}"
    patterns.append(rf"rgba?\(\s*{channels}\s*(?:{sep}[\d.]+%?\s*)?\)")
    patterns.append(rf"rgba?\(\s*{channels_spaced}\s*(?:/\s*[\d.]+%?\s*)?\)")
    return patterns
