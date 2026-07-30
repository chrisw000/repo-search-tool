"""The matching strategy seam.

Whole-image signature matching cannot find a logo composited as a small region
inside a larger image — a banner, a screenshot, a hero — because the
surrounding content dominates the signature. That is a real limitation, not a
threshold to tune, and detecting it needs a different technique entirely
(edge-based multi-scale template matching being the more reliable option for
flat wordmarks, which throw too few keypoints for feature matching).

Solving it is out of scope here. This interface is what lets it be added later
without touching acquisition, configuration, or reporting: a new strategy
implements `MatchStrategy`, registers a name, and its matches reach reports
through the same `ImageMatch` shape.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image

from brandscan.config.model import ReferenceImage
from brandscan.images.hashing import hamming_distance, signature_for
from brandscan.images.loader import ImageLoadError, open_image


@dataclass(frozen=True)
class ImageMatch:
    """One candidate matching one reference, with the measured distance."""

    label: str
    distance: int


class MatchStrategy(ABC):
    """Decides whether a candidate image depicts a reference layout."""

    name: str = "abstract"

    @abstractmethod
    def prepare(self, references: list[ReferenceImage]) -> list[str]:
        """Ingest the reference set. Returns any references that failed to load."""

    @abstractmethod
    def match(self, image: Image.Image) -> list[ImageMatch]:
        """Return matches within threshold, closest first."""

    @property
    @abstractmethod
    def ready(self) -> bool:
        """Whether any reference was successfully ingested."""


class PerceptualHashStrategy(MatchStrategy):
    """Whole-image perceptual hashing over trimmed luminance.

    Filename, path, format, and pixel dimensions play no part in the decision:
    the signature is computed from content alone, which is what makes a renamed,
    reformatted, resized, recoloured, or repadded copy still match.
    """

    name = "perceptual-hash"

    def __init__(self, threshold: int) -> None:
        self.threshold = threshold
        self._signatures: list[tuple[str, int]] = []

    def prepare(self, references: list[ReferenceImage]) -> list[str]:
        failures: list[str] = []
        for reference in references:
            try:
                image = open_image(reference.path)
            except ImageLoadError as exc:
                failures.append(f"{reference.path.name}: {exc}")
                continue
            self._signatures.append((reference.label, signature_for(image)))
        return failures

    @property
    def ready(self) -> bool:
        return bool(self._signatures)

    def match(self, image: Image.Image) -> list[ImageMatch]:
        if not self._signatures:
            return []
        candidate = signature_for(image)
        matches = [
            ImageMatch(label=label, distance=hamming_distance(candidate, signature))
            for label, signature in self._signatures
        ]
        within = [m for m in matches if m.distance <= self.threshold]
        # Closest reference first, so a reader sees the most likely layout at
        # the top when a candidate sits near several references.
        within.sort(key=lambda m: (m.distance, m.label))
        return within


STRATEGIES: dict[str, type[MatchStrategy]] = {
    PerceptualHashStrategy.name: PerceptualHashStrategy,
}


def build_strategy(threshold: int, name: str = PerceptualHashStrategy.name) -> MatchStrategy:
    try:
        factory = STRATEGIES[name]
    except KeyError:
        known = ", ".join(sorted(STRATEGIES))
        raise ValueError(f"unknown matching strategy {name!r}; known: {known}") from None
    return factory(threshold)  # type: ignore[call-arg]
