"""Enumerating and opening candidate images.

Coverage spans raster formats, icon containers, vector images, and images
recovered from base64 data URIs. Everything is returned as opened — never
converted — because the trim that follows depends on seeing the original mode.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFile

from brandscan.images.raster import RasterisationError, rasterise_svg, rasterise_svg_bytes

# Legacy repositories carry a fair number of subtly truncated images. Reading
# what is there beats discarding the file.
ImageFile.LOAD_TRUNCATED_IMAGES = True

RASTER_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff",
}
ICON_SUFFIXES = {".ico", ".cur"}
VECTOR_SUFFIXES = {".svg"}
IMAGE_SUFFIXES = RASTER_SUFFIXES | ICON_SUFFIXES | VECTOR_SUFFIXES


class ImageLoadError(Exception):
    """One image could not be decoded. Recorded, never fatal."""


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_SUFFIXES


def open_image(path: Path) -> Image.Image:
    """Open an image file without altering its colour mode."""
    suffix = path.suffix.lower()
    if suffix in VECTOR_SUFFIXES:
        try:
            return rasterise_svg(path)
        except RasterisationError as exc:
            raise ImageLoadError(str(exc)) from exc

    try:
        image = Image.open(path)
        image.load()
    except (OSError, ValueError, SyntaxError) as exc:
        raise ImageLoadError(f"image could not be decoded: {exc}") from exc

    if image.size[0] <= 0 or image.size[1] <= 0:
        raise ImageLoadError("image has no pixels")
    return image


def open_image_bytes(data: bytes, subtype: str = "") -> Image.Image:
    """Open an image recovered from a data URI."""
    import io

    if "svg" in subtype.lower():
        try:
            return rasterise_svg_bytes(data)
        except RasterisationError as exc:
            raise ImageLoadError(str(exc)) from exc

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (OSError, ValueError, SyntaxError) as exc:
        raise ImageLoadError(f"embedded image could not be decoded: {exc}") from exc

    if image.size[0] <= 0 or image.size[1] <= 0:
        raise ImageLoadError("embedded image has no pixels")
    return image
