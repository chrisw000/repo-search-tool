"""Images inlined into text files as base64 data URIs.

An inlined logo has no filename to search and no image file to enumerate, so
without this it would be invisible to both search capabilities. Decoding it and
handing the bytes to image matching means it is found by its content, exactly
like a logo sitting on disk.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass

# Payloads shorter than this are never a real image and are usually a fragment
# of some other encoded value that happens to sit after a `base64,`.
MIN_PAYLOAD_CHARS = 64

_DATA_URI = re.compile(
    r"data:image/(?P<subtype>[\w.+-]+)\s*;\s*base64\s*,\s*(?P<payload>[A-Za-z0-9+/=]{%d,})"
    % MIN_PAYLOAD_CHARS,
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EmbeddedImage:
    """An image recovered from a text file, with where it was found."""

    containing_path: str
    line: int
    subtype: str
    data: bytes


def _decode(payload: str) -> bytes | None:
    """Decode a base64 payload, tolerating missing padding.

    Returns None rather than raising: an undecodable payload is skipped, and
    the scan of the containing file continues.
    """
    stripped = payload.strip()
    padding = (-len(stripped)) % 4
    try:
        return base64.b64decode(stripped + "=" * padding, validate=True)
    except (binascii.Error, ValueError):
        return None


def find_embedded_images(
    relative_path: str, lines: list[str]
) -> tuple[list[EmbeddedImage], list[tuple[int, str]]]:
    """Extract every decodable base64 image from one file's lines.

    Returns the recovered images and, separately, the payloads that could not
    be decoded — recorded as issues rather than discarded, because a silent
    skip is indistinguishable from a file with nothing in it.
    """
    images: list[EmbeddedImage] = []
    failures: list[tuple[int, str]] = []

    for number, line in enumerate(lines, start=1):
        for match in _DATA_URI.finditer(line):
            data = _decode(match.group("payload"))
            if data is None:
                failures.append((number, "base64 image payload could not be decoded"))
                continue
            images.append(
                EmbeddedImage(
                    containing_path=relative_path,
                    line=number,
                    subtype=match.group("subtype").lower(),
                    data=data,
                )
            )
    return images, failures
