"""Image matching: filename independence, trimming, and colour independence."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from brandscan.config.model import ReferenceImage
from brandscan.images.hashing import hamming_distance, signature_for
from brandscan.images.loader import ImageLoadError, open_image
from brandscan.images.raster import rasterise_svg_bytes
from brandscan.images.strategy import PerceptualHashStrategy
from brandscan.images.trim import content_bbox, trim_to_content
from tests.conftest import draw_logo, draw_stacked_logo, pad

THRESHOLD = 10


def distance(left: Image.Image, right: Image.Image) -> int:
    return hamming_distance(signature_for(left), signature_for(right))


# --- Content bounding-box trimming ---------------------------------------


def test_transparent_padding_is_trimmed():
    logo = draw_logo(background=None)
    padded = pad(logo, 60)
    # Both sides trim to the same content, whatever transparent margin the
    # drawing itself happens to leave.
    assert trim_to_content(padded).size == trim_to_content(logo).size


def test_solid_colour_padding_is_trimmed_on_an_opaque_image():
    """The case D2 warns about: a fully opaque image must still trim.

    Converting to RGBA before measuring would hand the trim a full-frame alpha
    channel, it would find content everywhere, and it would silently become a
    no-op. The trim therefore reads the image as opened.
    """
    logo = draw_logo(background=(255, 255, 255))
    padded = pad(logo, 80, colour=(255, 255, 255))
    assert padded.mode == "RGB"

    trimmed = trim_to_content(padded)
    assert trimmed.size[0] < padded.size[0]
    assert trimmed.size[1] < padded.size[1]


def test_trimming_survives_a_prior_mode_conversion():
    """Even if something upstream converted first, the trim must still work.

    A full-frame alpha channel says nothing about where the content is, so the
    solid-colour path takes over rather than the trim degrading to a no-op.
    """
    padded = pad(draw_logo(background=(255, 255, 255)), 80, colour=(255, 255, 255))
    converted = padded.convert("RGBA")
    bbox = content_bbox(converted)
    assert bbox is not None
    assert bbox != (0, 0, *converted.size)


def test_anti_aliased_border_does_not_defeat_the_trim():
    logo = draw_logo(background=(255, 255, 255))
    padded = pad(logo, 40, colour=(255, 255, 255))
    # A faint gradient where padding meets content, as anti-aliasing produces.
    faint = padded.copy()
    pixels = faint.load()
    for x in range(faint.size[0]):
        pixels[x, 39] = (252, 252, 252)
        pixels[x, faint.size[1] - 40] = (252, 252, 252)

    trimmed = trim_to_content(faint)
    assert trimmed.size[0] < faint.size[0]


def test_padding_does_not_change_the_signature():
    """The whole point of trimming: padding must not shift the signature."""
    logo = draw_logo(background=(255, 255, 255))
    lightly_padded = pad(logo, 20, colour=(255, 255, 255))
    heavily_padded = pad(logo, 140, colour=(255, 255, 255))
    assert distance(lightly_padded, heavily_padded) <= THRESHOLD


def test_uniform_image_is_left_whole():
    blank = Image.new("RGB", (64, 64), (255, 255, 255))
    assert trim_to_content(blank).size == (64, 64)


# --- Colour independence --------------------------------------------------


def test_recoloured_copy_has_the_same_signature():
    original = draw_logo(foreground=(15, 98, 254), accent=(255, 107, 0))
    recoloured = draw_logo(foreground=(200, 30, 30), accent=(30, 160, 90))
    assert distance(original, recoloured) <= THRESHOLD


def test_identical_image_is_at_distance_zero():
    logo = draw_logo()
    assert distance(logo, logo.copy()) == 0


# --- Filename, format, and size independence ------------------------------


def test_resized_copy_still_matches():
    original = draw_logo((240, 120))
    resized = draw_logo((720, 360))
    assert distance(original, resized) <= THRESHOLD


def test_reformatted_copy_still_matches(tmp_path: Path):
    logo = draw_logo()
    as_png = tmp_path / "unrelated-name.png"
    as_jpeg = tmp_path / "sprite-2.jpg"
    logo.save(as_png)
    logo.save(as_jpeg, quality=92)
    assert distance(open_image(as_png), open_image(as_jpeg)) <= THRESHOLD


@pytest.mark.parametrize("fmt,suffix,kwargs", [
    ("PNG", ".png", {}),
    ("JPEG", ".jpg", {"quality": 75}),
    ("GIF", ".gif", {}),
    ("WEBP", ".webp", {}),
    ("BMP", ".bmp", {}),
    ("TIFF", ".tiff", {}),
])
def test_a_larger_differently_shaped_copy_matches_in_any_format(
    tmp_path: Path, fmt: str, suffix: str, kwargs: dict
):
    """Reference trims to 200x100; candidate is bigger and not the same aspect.

    A real asset is rarely a clean multiple of the reference: it sits on some
    larger canvas at whatever proportions the designer used. Neither the size
    difference nor the aspect difference may decide the match.
    """
    content = trim_to_content(draw_logo((800, 400))).convert("RGB")
    reference = content.resize((200, 100), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (500, 500), (255, 255, 255))
    canvas.paste(content.resize((400, 190), Image.Resampling.LANCZOS), (50, 155))

    candidate_path = tmp_path / f"asset{suffix}"
    canvas.save(candidate_path, format=fmt, **kwargs)

    assert distance(reference, open_image(candidate_path)) <= THRESHOLD


@pytest.mark.parametrize("height", [200, 190, 160, 133, 100, 80])
def test_aspect_ratio_does_not_decide_the_match(height: int):
    """Proportions are normalised away by the fixed hashing grid.

    Worth pinning down explicitly: it is what lets a squashed or stretched copy
    match, and equally why two layouts must differ in *arrangement* rather than
    merely in proportions to be told apart.
    """
    content = trim_to_content(draw_logo((800, 400))).convert("RGB")
    reference = content.resize((200, 100), Image.Resampling.LANCZOS)
    candidate = content.resize((400, height), Image.Resampling.LANCZOS)
    assert distance(reference, candidate) <= THRESHOLD


def test_distinct_layouts_do_not_match_each_other():
    """A horizontal lockup must not be reported as the stacked one.

    Because proportions are discarded, layouts are distinguished only by where
    their elements sit. This is the assertion that would fail if the two
    reference fixtures were the same composition in different frames.
    """
    horizontal = draw_logo((240, 120))
    stacked = draw_stacked_logo((120, 240))
    assert distance(horizontal, stacked) > THRESHOLD * 2


def test_each_layout_still_matches_its_own_variants():
    """The separation above must not come at the cost of within-layout recall."""
    stacked = draw_stacked_logo((120, 240))
    for variant in (
        draw_stacked_logo((400, 800)),
        draw_stacked_logo((300, 300)),
        draw_stacked_logo((120, 240), foreground=(200, 30, 30), accent=(20, 160, 90)),
    ):
        assert distance(stacked, variant) <= THRESHOLD


def test_icon_container_is_readable(tmp_path: Path):
    icon = tmp_path / "favicon.ico"
    draw_logo((64, 64)).save(icon, sizes=[(64, 64)])
    assert open_image(icon).size[0] > 0


def test_malformed_image_raises_a_recorded_failure(tmp_path: Path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"\x89PNG\r\n\x1a\n not actually a png")
    with pytest.raises(ImageLoadError):
        open_image(broken)


# --- Vector images --------------------------------------------------------

SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="240" height="120" viewBox="0 0 240 120">
  <title>Contoso</title>
  <rect x="19" y="24" width="53" height="72" fill="#0F62FE"/>
  <ellipse cx="110" cy="60" rx="29" ry="26" fill="#0F62FE"/>
  <polygon points="149,90 178,26 216,90" fill="#FF6B00"/>
  <rect x="149" y="96" width="67" height="10" fill="#0F62FE"/>
</svg>
"""


def test_vector_rasterises_and_matches_its_raster_twin():
    rendered = rasterise_svg_bytes(SVG.encode("utf-8"))
    assert rendered.size[0] > 0
    assert distance(rendered, draw_logo()) <= THRESHOLD


def test_malformed_vector_is_reported_not_raised_as_a_crash(tmp_path: Path):
    broken = tmp_path / "broken.svg"
    broken.write_text("<svg><this is not xml", encoding="utf-8")
    with pytest.raises(ImageLoadError):
        open_image(broken)


# --- Threshold-governed matching -----------------------------------------


def test_matches_are_ordered_by_increasing_distance(reference_dir: Path):
    strategy = PerceptualHashStrategy(threshold=64)
    references = [
        ReferenceImage(path=reference_dir / "logo-horizontal.png", label="horizontal-lockup"),
        ReferenceImage(path=reference_dir / "logo-stacked.png", label="stacked-lockup"),
    ]
    assert strategy.prepare(references) == []

    matches = strategy.match(draw_logo((240, 120)))
    assert len(matches) == 2
    assert matches[0].label == "horizontal-lockup"
    assert matches[0].distance <= matches[1].distance
    # The references are distinct layouts, so the ordering reflects a real gap
    # rather than two near-identical images landing in an arbitrary order.
    assert matches[1].distance - matches[0].distance > THRESHOLD


def test_at_the_default_threshold_only_the_right_layout_matches(reference_dir: Path):
    strategy = PerceptualHashStrategy(threshold=THRESHOLD)
    strategy.prepare(
        [
            ReferenceImage(path=reference_dir / "logo-horizontal.png", label="horizontal-lockup"),
            ReferenceImage(path=reference_dir / "logo-stacked.png", label="stacked-lockup"),
        ]
    )
    assert [m.label for m in strategy.match(draw_logo((600, 300)))] == ["horizontal-lockup"]
    assert [m.label for m in strategy.match(draw_stacked_logo((300, 600)))] == [
        "stacked-lockup"
    ]


def test_candidate_outside_the_threshold_is_not_reported(reference_dir: Path):
    strategy = PerceptualHashStrategy(threshold=2)
    strategy.prepare(
        [ReferenceImage(path=reference_dir / "logo-horizontal.png", label="horizontal-lockup")]
    )
    noise = Image.new("RGB", (200, 200), (255, 255, 255))
    noise.paste(Image.new("RGB", (30, 180), (0, 0, 0)), (10, 10))
    assert strategy.match(noise) == []


def test_lowering_the_threshold_yields_a_subset(reference_dir: Path):
    references = [
        ReferenceImage(path=reference_dir / "logo-horizontal.png", label="horizontal-lockup"),
        ReferenceImage(path=reference_dir / "logo-stacked.png", label="stacked-lockup"),
    ]
    candidate = draw_logo((300, 150), foreground=(90, 90, 90))

    permissive = PerceptualHashStrategy(threshold=40)
    permissive.prepare(references)
    strict = PerceptualHashStrategy(threshold=4)
    strict.prepare(references)

    loose_labels = {m.label for m in permissive.match(candidate)}
    tight_labels = {m.label for m in strict.match(candidate)}
    assert tight_labels <= loose_labels
