"""Running image matching across one repository.

Image findings are always high severity: a logo is the most visible and least
ambiguous piece of a rebrand, and unlike a brand name in a comment there is no
reading under which it can be left alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from brandscan.config.model import ScanScope, Severity
from brandscan.findings import Finding, MatchType, ScanIssue
from brandscan.images.loader import ImageLoadError, is_image_path, open_image, open_image_bytes
from brandscan.images.strategy import MatchStrategy
from brandscan.scan.embedded import EmbeddedImage
from brandscan.scan.walker import FileWalker

IMAGE_SEVERITY = Severity.HIGH

IMAGE_REMEDIATION = (
    "Replace this asset with the corresponding new-brand image, keeping the "
    "same path and filename where anything references it by name. Check the "
    "surrounding markup for alt text and captions naming the old brand."
)

EMBEDDED_REMEDIATION = (
    "This logo is inlined as a base64 data URI rather than stored as a file. "
    "Re-encode the replacement asset and substitute the data URI in place, or "
    "move the image to a file and reference it."
)


@dataclass
class ImageScanResult:
    findings: list[Finding] = field(default_factory=list)
    issues: list[ScanIssue] = field(default_factory=list)
    images_examined: int = 0


def _findings_for(
    strategy: MatchStrategy,
    image,
    relative_path: str,
    line: int | None = None,
    embedded_in: str | None = None,
) -> list[Finding]:
    remediation = EMBEDDED_REMEDIATION if embedded_in else IMAGE_REMEDIATION
    return [
        Finding(
            match_type=MatchType.IMAGE,
            matched=match.label,
            path=relative_path,
            line=line,
            severity=IMAGE_SEVERITY,
            distance=match.distance,
            remediation=remediation,
            embedded_in=embedded_in,
        )
        for match in strategy.match(image)
    ]


def scan_images(
    root: Path,
    scope: ScanScope,
    strategy: MatchStrategy,
    embedded: list[EmbeddedImage] | None = None,
) -> ImageScanResult:
    """Match every image in a repository, including inlined ones.

    Every decode is isolated: an undecodable file or an unrenderable vector is
    recorded as an issue and the remaining images are still matched.
    """
    result = ImageScanResult()
    if not strategy.ready:
        return result

    walker = FileWalker(root=root, scope=scope)
    for path in walker.iter_files():
        if not is_image_path(path):
            continue
        relative = walker.relative(path)
        try:
            image = open_image(path)
        except ImageLoadError as exc:
            result.issues.append(ScanIssue(path=relative, reason=str(exc)))
            continue
        except Exception as exc:  # a decoder can fail in ways it does not declare
            result.issues.append(
                ScanIssue(path=relative, reason=f"image could not be decoded: {exc}")
            )
            continue

        result.images_examined += 1
        result.findings.extend(_findings_for(strategy, image, relative))

    for item in embedded or []:
        try:
            image = open_image_bytes(item.data, item.subtype)
        except ImageLoadError as exc:
            result.issues.append(
                ScanIssue(path=item.containing_path, reason=str(exc), line=item.line)
            )
            continue
        except Exception as exc:
            result.issues.append(
                ScanIssue(
                    path=item.containing_path,
                    reason=f"embedded image could not be decoded: {exc}",
                    line=item.line,
                )
            )
            continue

        result.images_examined += 1
        result.findings.extend(
            _findings_for(
                strategy,
                image,
                item.containing_path,
                line=item.line,
                embedded_in=item.containing_path,
            )
        )

    result.findings.sort(key=lambda finding: (finding.sort_key, finding.distance or 0))
    return result
