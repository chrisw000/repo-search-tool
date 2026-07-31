"""Rasterising vector images onto a fixed canvas.

Vectors go through exactly the same trim-and-hash path as raster images once
rendered, so nothing downstream needs to know an image was ever an SVG. A
malformed SVG is a per-file failure: rasterisation is a large surface and one
bad file must not end a repository's scan.
"""

from __future__ import annotations

import io
import warnings

from PIL import Image

CANVAS = 512


class RasterisationError(Exception):
    """One vector image could not be rendered."""


def _render(drawing) -> Image.Image:
    from reportlab.graphics import renderPM

    width = float(getattr(drawing, "width", 0) or 0)
    height = float(getattr(drawing, "height", 0) or 0)
    if width <= 0 or height <= 0:
        raise RasterisationError("vector image reports no usable dimensions")

    # A fixed canvas keeps every vector comparable with every raster, and keeps
    # a 4000pt illustration from allocating a bitmap to match.
    scale = CANVAS / max(width, height)
    drawing.scale(scale, scale)
    drawing.width = width * scale
    drawing.height = height * scale

    return renderPM.drawToPIL(drawing, dpi=72, bg=0xFFFFFF)


def rasterise_svg_bytes(data: bytes) -> Image.Image:
    """Render SVG source into a raster image."""
    from svglib.svglib import svg2rlg

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            drawing = svg2rlg(io.BytesIO(data))
    except Exception as exc:  # svglib raises a wide range of parser errors
        raise RasterisationError(f"vector image could not be parsed: {exc}") from exc

    if drawing is None:
        raise RasterisationError("vector image could not be parsed")

    try:
        return _render(drawing)
    except RasterisationError:
        raise
    except Exception as exc:
        raise RasterisationError(f"vector image could not be rendered: {exc}") from exc
