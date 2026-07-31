"""Enumerating and opening candidate images.

Coverage spans raster formats, icon containers, vector images, and images
recovered from base64 data URIs. Everything is returned as opened — never
converted — because the trim that follows depends on seeing the original mode.

This module is also the only place that decides *why* an input was not matched.
The code that opened the file is the only code that knows; spreading that
inference to the callers would mean two places re-deriving it, and they would
disagree the first time a new case appeared.

There are two such whys, and they are different in kind. An input that could
not be *read* raises `ImageLoadError` carrying a classified cause. An input
read perfectly well and too small to carry a layout raises `ImageBelowMinimum`,
which carries no cause because nothing about it is broken.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageFile

from brandscan.findings import UnreadableCause
from brandscan.images.classify import classify_bytes
from brandscan.images.raster import RasterisationError, rasterise_svg_bytes
from brandscan.images.trim import content_bbox
from brandscan.logging_setup import processing

# Legacy repositories carry a fair number of subtly truncated images. Reading
# what is there beats discarding the file — but a truncated file that yields
# nothing at all is a failed read, not an image that was examined and found
# empty, which is what the blank check below is for.
ImageFile.LOAD_TRUNCATED_IMAGES = True

RASTER_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff",
}
ICON_SUFFIXES = {".ico", ".cur"}
VECTOR_SUFFIXES = {".svg"}
IMAGE_SUFFIXES = RASTER_SUFFIXES | ICON_SUFFIXES | VECTOR_SUFFIXES


class ImageLoadError(Exception):
    """One image could not be read. Recorded, never fatal.

    Carries the classified cause alongside the free-text reason: the cause is
    what the report groups and acts on, the reason is the decoder's own message,
    which is the only real evidence when the cause is `MALFORMED`.
    """

    def __init__(self, reason: str, cause: UnreadableCause = UnreadableCause.MALFORMED):
        super().__init__(reason)
        self.reason = reason
        self.cause = cause


class ImageBelowMinimum(Exception):
    """One image was read perfectly well and is too small to assess.

    Deliberately *not* an `ImageLoadError`, and deliberately without an
    `UnreadableCause`. Every member of that enum names something that went
    wrong and carries a remediation for making the input assessable; a 1x1
    spacer is not broken and no remedy applies to it. Given a cause it would
    land in the report's unread section, which is the noise the minimum exists
    to remove.
    """

    def __init__(self, size: tuple[int, int], minimum: int):
        super().__init__(
            f"image is {size[0]}x{size[1]}, below the {minimum}px minimum"
        )
        self.size = size
        self.minimum = minimum


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_SUFFIXES


def _reject(cause: UnreadableCause, label: str) -> ImageLoadError:
    """Turn a byte-level classification into the error the callers record."""
    described = {
        # Named as a skip rather than a failure: a placeholder somebody
        # committed on purpose is an ordinary thing to find in a repository.
        UnreadableCause.EMPTY: f"{label} is empty; skipped without decoding",
        UnreadableCause.VCS_POINTER: (
            f"{label} is a version-control pointer; its content was never fetched"
        ),
        UnreadableCause.NOT_AN_IMAGE: f"{label} does not contain image data",
    }[cause]
    return ImageLoadError(described, cause)


def _decode(data: bytes, vector: bool, label: str) -> Image.Image:
    """Decode bytes already judged worth handing to a decoder."""
    if vector:
        try:
            return rasterise_svg_bytes(data)
        except RasterisationError as exc:
            raise ImageLoadError(str(exc), UnreadableCause.MALFORMED) from exc

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (OSError, ValueError, SyntaxError) as exc:
        raise ImageLoadError(
            f"{label} could not be decoded: {exc}", UnreadableCause.MALFORMED
        ) from exc

    if image.size[0] <= 0 or image.size[1] <= 0:
        raise ImageLoadError(f"{label} has no pixels", UnreadableCause.MALFORMED)
    return image


def _load(
    data: bytes, vector: bool, label: str, origin: str, min_dimension: int = 0
) -> Image.Image:
    """Classify, then decode, then size, then check the result carries content.

    The classification runs first so that a parser which would log about a file
    it cannot name is never reached. The blank check runs last and reuses
    `content_bbox` — the machinery that decides where to trim is the same
    machinery that decides whether there is anything to trim, so the two cannot
    drift apart.

    The size gate sits between them, and the order is the decision rather than
    an accident of statement order: a one-pixel transparent spacer trips both
    tests, and *undersized* is the more specific and more useful account of it.
    Reported as blank it would tell an operator to confirm whether it should
    have held artwork; reported as undersized it needs no reply at all.
    """
    cause = classify_bytes(data, vector=vector)
    if cause is not None:
        raise _reject(cause, label)

    with processing(origin):
        image = _decode(data, vector, label)

    if min_dimension > 0 and min(image.size) < min_dimension:
        raise ImageBelowMinimum(image.size, min_dimension)

    if content_bbox(image) is None:
        raise ImageLoadError(
            f"{label} decoded but rendered no content", UnreadableCause.RENDERED_BLANK
        )
    return image


def open_image(path: Path, min_dimension: int = 0) -> Image.Image:
    """Open an image file without altering its colour mode.

    `min_dimension` is the *effective* minimum for this candidate, resolved by
    the caller: this module knows sizes, not paths, so an exempted path arrives
    here as a minimum of 0.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ImageLoadError(
            f"image could not be read: {exc}", UnreadableCause.MALFORMED
        ) from exc

    return _load(
        data,
        vector=path.suffix.lower() in VECTOR_SUFFIXES,
        label="image",
        origin=str(path),
        min_dimension=min_dimension,
    )


def open_image_bytes(
    data: bytes, subtype: str = "", origin: str = "", min_dimension: int = 0
) -> Image.Image:
    """Open an image recovered from a data URI.

    Classified exactly as a file on disk is: an inlined payload can be a
    placeholder or a fragment of something that is not an image just as easily,
    and it is ruled out by size on the same terms.
    """
    return _load(
        data,
        vector="svg" in subtype.lower(),
        label="embedded image",
        origin=origin or "embedded image",
        min_dimension=min_dimension,
    )
