"""The similarity signature.

Hashing over luminance is colour-blind by construction, which is exactly what a
rebrand wants: the reference set needs one image per distinct *layout* rather
than one per colourway, and recoloured copies nobody catalogued are caught for
free. An exact copy of a reference lands at distance 0, so no separate
byte-comparison pass is needed for detection.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from brandscan.images.trim import DEFAULT_FUZZ, trim_to_content

# 32x32 feeds the DCT; the low-frequency 8x8 corner becomes the 64-bit hash.
HASH_SIZE = 8
DCT_SIZE = 32


def _dct_matrix(size: int) -> np.ndarray:
    """Basis for a 2-D DCT-II.

    Scaling factors are omitted deliberately: the hash thresholds coefficients
    against their own median, so any uniform scaling cancels out.
    """
    indices = np.arange(size)
    return np.cos(np.pi * (2 * indices[None, :] + 1) * indices[:, None] / (2 * size))


_DCT = _dct_matrix(DCT_SIZE)


def perceptual_hash(grayscale: Image.Image) -> int:
    """Compute a 64-bit perceptual hash of an already-grayscale image."""
    resized = grayscale.resize((DCT_SIZE, DCT_SIZE), Image.Resampling.LANCZOS)
    pixels = np.asarray(resized, dtype=np.float64)
    coefficients = _DCT @ pixels @ _DCT.T
    # Drop the DC term: it encodes overall brightness, not layout.
    low_frequency = coefficients[:HASH_SIZE, :HASH_SIZE]
    values = low_frequency.flatten()
    median = np.median(values[1:])
    bits = values > median

    result = 0
    for bit in bits:
        result = (result << 1) | int(bit)
    return result


def signature_for(image: Image.Image, fuzz: int = DEFAULT_FUZZ) -> int:
    """Turn an image as opened into its comparable signature.

    The only supported entry point, because it fixes the required order: trim
    the image as it was opened, and only then convert to luminance. Converting
    first would introduce a full-frame alpha channel and silently disable the
    trim.
    """
    trimmed = trim_to_content(image, fuzz)
    grayscale = trimmed.convert("L")
    return perceptual_hash(grayscale)


def hamming_distance(left: int, right: int) -> int:
    """Bits differing between two signatures — the similarity distance."""
    return int((left ^ right).bit_count())
