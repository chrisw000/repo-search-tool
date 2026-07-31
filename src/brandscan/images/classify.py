"""Judging an input's bytes before any decoder sees them.

Everything here works on bytes alone and never invokes a parser, which is what
makes the third-party noise disappear at source: a decoder that is never called
cannot log. It is also the cheapest possible check, and it runs against every
image in every repository.

What it can decide, it decides. What it cannot, it declines to guess about —
the file falls through to the decoder exactly as it did before, and a decoder
failure is classified as malformed by the caller.
"""

from __future__ import annotations

import codecs
import re

from brandscan.findings import UnreadableCause

# Longest first: the UTF-32 LE mark begins with the UTF-16 LE mark, so testing
# the shorter one first would leave two stray NUL bytes behind and the file
# would not read as empty.
_BYTE_ORDER_MARKS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)

# Markup that carries no content of its own. Stripped repeatedly rather than
# once, because a declaration may be followed by comments and vice versa.
_EMPTY_MARKUP = (
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"<\?.*?\?>", re.DOTALL),
    re.compile(r"<!DOCTYPE[^>\[]*(?:\[[^\]]*\])?\s*>", re.DOTALL | re.IGNORECASE),
)

# The first line of a Git LFS pointer. The spec fixes this as the first key, so
# it is the whole of the test — the oid and size lines that follow vary.
_LFS_POINTER = re.compile(rb"^\s*version https://(?:git-lfs\.github\.com|hawser)/spec/", re.I)

# Enough to recognise the formats this scanner enumerates. A file whose bytes
# start with none of these is not necessarily broken, so absence alone decides
# nothing — it only permits the is-this-text question to be asked.
_MAGIC: tuple[bytes, ...] = (
    b"\x89PNG\r\n\x1a\n",       # PNG
    b"\xff\xd8\xff",            # JPEG
    b"GIF87a",
    b"GIF89a",
    b"BM",                      # BMP
    b"RIFF",                    # WebP container
    b"II*\x00",                 # TIFF, little-endian
    b"MM\x00*",                 # TIFF, big-endian
    b"\x00\x00\x01\x00",        # ICO
    b"\x00\x00\x02\x00",        # CUR
)

# How much of an oversized file is inspected. A placeholder, a pointer, and an
# error page are all small; reading a 50 MB TIFF in full to ask whether it is
# whitespace would cost more than the question is worth.
_INSPECT_BYTES = 64 * 1024


def _as_text(data: bytes) -> str | None:
    """Decode as text, or None if the bytes are not text at all.

    Binary image data almost never decodes cleanly, which is what makes this a
    safe gate in front of both the emptiness and the not-an-image tests.
    """
    body, encoding, marked = data, "utf-8", False
    for mark, mark_encoding in _BYTE_ORDER_MARKS:
        if data.startswith(mark):
            body, encoding, marked = data[len(mark) :], mark_encoding, True
            break
    # A mark on its own is a file somebody's editor created and never filled in.
    # The trailing NULs are the padding of a wide encoding, not content.
    if marked and not body.translate(None, b"\x00").strip():
        return ""
    try:
        return body.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return None


def _strip_empty_markup(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        for pattern in _EMPTY_MARKUP:
            text = pattern.sub("", text)
    # A mark decoded into the text rather than stripped from the bytes: a file
    # holding one and nothing else is still empty.
    return text.strip().strip("﻿").strip()


def is_empty(data: bytes) -> bool:
    """Whether an input carries no content at all.

    True for no bytes, and for nothing but whitespace, a byte-order mark, a
    document declaration, or comments. A comment-only `artwork pending` stub is
    deliberately empty rather than malformed: somebody committed it on purpose,
    and reporting a placeholder as a defect trains an operator to ignore the
    section it appears in.
    """
    if not data.strip():
        return True
    if len(data) > _INSPECT_BYTES:
        return False
    text = _as_text(data)
    if text is None:
        return False
    return not _strip_empty_markup(text)


def _is_vcs_pointer(data: bytes) -> bool:
    return bool(_LFS_POINTER.match(data[:_INSPECT_BYTES]))


def _is_not_an_image(data: bytes, vector: bool) -> bool:
    """Whether the content is plainly something other than an image.

    An error page saved under an image's name is the case that matters: it is
    ordinary text, so it decodes, and a vector file that never mentions `<svg`
    is not one either.
    """
    head = data[:_INSPECT_BYTES]
    text = _as_text(head)
    if text is None:
        return False
    if vector:
        return "<svg" not in text.lower()
    # Readable text under a raster extension is not a raster image, unless its
    # bytes say otherwise — a few formats do begin with printable ASCII.
    return not any(head.startswith(magic) for magic in _MAGIC)


def classify_bytes(data: bytes, vector: bool = False) -> UnreadableCause | None:
    """Classify an input from its bytes, or None if a decoder should decide.

    Order matters: an empty file is empty whatever extension it carries, and a
    pointer is a pointer before it is judged as not-an-image.
    """
    if is_empty(data):
        return UnreadableCause.EMPTY
    if _is_vcs_pointer(data):
        return UnreadableCause.VCS_POINTER
    if _is_not_an_image(data, vector):
        return UnreadableCause.NOT_AN_IMAGE
    return None
