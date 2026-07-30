"""Trimming an image to its content bounding box.

Perceptual hashing normalises the *whole frame* onto a fixed grid. The same
logo at 100% and at 60% inside padding lands its features in different cells
and produces a different signature, so both reference and candidate are trimmed
to their content before anything else happens.

The ordering below is load-bearing, not incidental — see `trim_to_content`.
"""

from __future__ import annotations

from PIL import Image, ImageChops

# Anti-aliased edges fade into the padding over a few near-identical pixels.
# Without a tolerance those faint pixels count as content and the trim becomes
# a no-op on exactly the images that most need it.
DEFAULT_FUZZ = 12

_ALPHA_MODES = {"RGBA", "LA", "PA"}


def _has_alpha(image: Image.Image) -> bool:
    """Whether the image *as opened* carries transparency.

    This must be judged from the original mode and info. Asking after a
    conversion to RGBA always answers yes, which is the trap this whole module
    is arranged to avoid.
    """
    return image.mode in _ALPHA_MODES or "transparency" in image.info


def _alpha_bbox(image: Image.Image, fuzz: int) -> tuple[int, int, int, int] | None:
    source = image if image.mode in _ALPHA_MODES else image.convert("RGBA")
    alpha = source.getchannel("A")
    # Pixels at or below the fuzz level count as padding.
    mask = alpha.point(lambda value: 255 if value > fuzz else 0)
    return mask.getbbox()


def _corner_colour(image: Image.Image) -> tuple[int, ...]:
    """The padding colour, taken as the most common of the four corners.

    A single corner is enough until a logo happens to touch it; a majority of
    four is cheap and removes that failure.
    """
    width, height = image.size
    corners = [
        image.getpixel((0, 0)),
        image.getpixel((width - 1, 0)),
        image.getpixel((0, height - 1)),
        image.getpixel((width - 1, height - 1)),
    ]
    normalised = [c if isinstance(c, tuple) else (c,) for c in corners]
    return max(normalised, key=normalised.count)


def _solid_bbox(image: Image.Image, fuzz: int) -> tuple[int, int, int, int] | None:
    reference = image if image.mode in ("RGB", "L") else image.convert("RGB")
    corner = _corner_colour(reference)
    background = Image.new(reference.mode, reference.size, corner)
    difference = ImageChops.difference(reference, background)
    if difference.mode != "L":
        difference = difference.convert("L")
    mask = difference.point(lambda value: 255 if value > fuzz else 0)
    return mask.getbbox()


def content_bbox(image: Image.Image, fuzz: int = DEFAULT_FUZZ) -> tuple[int, int, int, int] | None:
    """Locate the content within its padding.

    Transparent padding is measured from the alpha channel; solid-colour
    padding from the difference against the padding colour. An image whose
    alpha channel is fully opaque falls through to the solid-colour path,
    because a full-frame alpha channel says nothing about where the content is.
    """
    if _has_alpha(image):
        bbox = _alpha_bbox(image, fuzz)
        if bbox is not None and bbox != (0, 0, *image.size):
            return bbox
        # Fully opaque despite carrying an alpha channel: the padding, if any,
        # is a solid colour rather than transparency.
    return _solid_bbox(image, fuzz)


def trim_to_content(image: Image.Image, fuzz: int = DEFAULT_FUZZ) -> Image.Image:
    """Crop an image to its content bounding box.

    **Call this on the image as opened, before any colour-mode conversion.**
    Converting an opaque image to RGBA first gives it a full-frame alpha
    channel; the trim then measures that channel, finds content everywhere, and
    silently becomes a no-op. Matching degrades with no error anywhere. This is
    the single easiest thing to get wrong in this pipeline, which is why the
    grayscale conversion needed for hashing lives *after* this call, inside
    `signature_for`, rather than at any caller.
    """
    bbox = content_bbox(image, fuzz)
    if bbox is None:
        # A uniform image has no content to isolate; leave it whole.
        return image
    if bbox == (0, 0, *image.size):
        return image
    return image.crop(bbox)
