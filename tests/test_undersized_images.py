"""The minimum candidate size: what is ruled out, what is exempt, what is kept.

An image a dozen pixels across has no layout for a perceptual hash to describe,
so a distance measured against it is not measuring resemblance. These cover the
gate that keeps such images out of matching, the favicon exemption that lets the
minimum be raised safely, and the accounting that stops a ruled-out image being
mistaken for one that was assessed and found clean.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from brandscan.config.model import ImageScope, ReferenceImage, ScanScope
from brandscan.findings import UnreadableCause
from brandscan.images.loader import (
    ImageBelowMinimum,
    ImageLoadError,
    open_image,
    open_image_bytes,
)
from brandscan.images.strategy import PerceptualHashStrategy
from brandscan.scan.embedded import EmbeddedImage
from brandscan.scan.image_search import scan_images
from tests.conftest import draw_logo

MINIMUM = 15


def scope() -> ScanScope:
    return ScanScope()


def strategy(reference_dir: Path) -> PerceptualHashStrategy:
    built = PerceptualHashStrategy(threshold=10)
    built.prepare(
        [
            ReferenceImage(
                path=reference_dir / "logo-horizontal.png", label="horizontal-lockup"
            )
        ]
    )
    return built


def marked(size: tuple[int, int]) -> Image.Image:
    """An image of a given size that actually carries content.

    A uniform fill would trim to nothing and be rejected as blank, which would
    test the wrong gate — so every candidate here has a mark in it, however few
    pixels it has to spare.
    """
    image = Image.new("RGB", size, (255, 255, 255))
    width, height = size
    # The left half, leaving at least one column of background so the trim has
    # an edge to find. A 1x1 cannot have content and does not need any: the
    # gate rules it out before the blank check is ever reached.
    ImageDraw.Draw(image).rectangle(
        [0, 0, (width - 1) // 2, height - 1], fill=(15, 98, 254)
    )
    return image


def write_png(path: Path, size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    marked(size).save(path)
    return path


def png_bytes(size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    marked(size).save(buffer, format="PNG")
    return buffer.getvalue()


# --- The gate itself ------------------------------------------------------


@pytest.mark.parametrize(
    "size",
    [(1, 1), (8, 8), (10, 10), (14, 14)],
    ids=["tracking-pixel", "bullet", "sprite-cell", "just-under"],
)
def test_an_image_below_the_minimum_in_both_dimensions_is_ruled_out(
    tmp_path: Path, size: tuple[int, int]
):
    path = write_png(tmp_path / "spacer.png", size)
    with pytest.raises(ImageBelowMinimum) as raised:
        open_image(path, min_dimension=MINIMUM)
    assert raised.value.size == size
    assert raised.value.minimum == MINIMUM


@pytest.mark.parametrize(
    "size", [(600, 1), (1, 400), (300, 14)], ids=["rule", "divider", "thin-banner"]
)
def test_an_image_below_the_minimum_in_one_dimension_is_ruled_out(
    tmp_path: Path, size: tuple[int, int]
):
    """Either dimension, not both and not area: a 600x1 rule has 600 pixels of
    area to spare and exactly as little layout as a 1x1."""
    path = write_png(tmp_path / "rule.png", size)
    with pytest.raises(ImageBelowMinimum):
        open_image(path, min_dimension=MINIMUM)


@pytest.mark.parametrize(
    "size", [(15, 15), (15, 200), (16, 16), (240, 120)], ids=["exact", "tall", "favicon", "logo"]
)
def test_an_image_at_or_above_the_minimum_is_admitted(
    tmp_path: Path, size: tuple[int, int]
):
    path = write_png(tmp_path / "candidate.png", size)
    assert open_image(path, min_dimension=MINIMUM).size == size


def test_a_zero_minimum_admits_everything(tmp_path: Path):
    path = write_png(tmp_path / "spacer.png", (4, 4))
    assert open_image(path, min_dimension=0).size == (4, 4)


def test_the_gate_precedes_the_blank_check(tmp_path: Path):
    """A 1x1 transparent spacer trips both tests. Undersized is the more
    specific account of it, and the more useful one: 'decoded to nothing' tells
    the operator to confirm whether it should have held artwork, which for a
    spacer is a demand to investigate something already known."""
    path = tmp_path / "spacer.png"
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(path)

    with pytest.raises(ImageBelowMinimum):
        open_image(path, min_dimension=MINIMUM)

    # And with no minimum in force it is still the blank read it always was.
    with pytest.raises(ImageLoadError) as blank:
        open_image(path, min_dimension=0)
    assert blank.value.cause is UnreadableCause.RENDERED_BLANK


def test_a_large_image_that_renders_nothing_is_still_a_failed_read(tmp_path: Path):
    """The gate narrows the blank check; it must not swallow it."""
    path = tmp_path / "blank.png"
    Image.new("RGBA", (240, 120), (0, 0, 0, 0)).save(path)

    with pytest.raises(ImageLoadError) as raised:
        open_image(path, min_dimension=MINIMUM)
    assert raised.value.cause is UnreadableCause.RENDERED_BLANK


def test_an_undersized_input_is_not_an_unreadable_one(tmp_path: Path):
    """`ImageBelowMinimum` is deliberately not an `ImageLoadError`: it carries no
    `UnreadableCause`, so it can never reach the report's unread section."""
    path = write_png(tmp_path / "spacer.png", (4, 4))
    with pytest.raises(ImageBelowMinimum) as raised:
        open_image(path, min_dimension=MINIMUM)
    assert not isinstance(raised.value, ImageLoadError)
    assert not hasattr(raised.value, "cause")


def test_an_inlined_image_is_gated_like_a_file():
    with pytest.raises(ImageBelowMinimum):
        open_image_bytes(png_bytes((1, 1)), "png", min_dimension=MINIMUM)
    assert open_image_bytes(png_bytes((32, 32)), "png", min_dimension=MINIMUM).size == (32, 32)


def test_reference_images_are_never_gated(reference_dir: Path):
    """The minimum filters incidental junk found in someone else's repository.
    A reference is a deliberate, labelled choice, and there is no junk in it."""
    tiny = reference_dir / "tiny-mark.png"
    marked((8, 8)).save(tiny)

    built = PerceptualHashStrategy(threshold=10)
    failures = built.prepare([ReferenceImage(path=tiny, label="tiny-mark")])

    assert not failures
    assert built.ready
    assert [match.label for match in built.match(marked((8, 8)))] == ["tiny-mark"]


# --- Applied across a repository ------------------------------------------


def test_undersized_candidates_are_counted_and_never_listed(
    tmp_path: Path, reference_dir: Path
):
    root = tmp_path / "repo"
    root.mkdir()
    for index in range(3):
        write_png(root / "assets" / f"spacer-{index}.png", (1, 1))
    draw_logo().save(root / "logo.png")

    result = scan_images(root, scope(), strategy(reference_dir), image_scope=ImageScope())

    assert result.images_below_minimum == 3
    assert result.images_examined == 1
    assert not result.issues, "an image ruled out by size was read perfectly well"
    assert [finding.matched for finding in result.findings] == ["horizontal-lockup"]


def test_an_undersized_copy_of_a_reference_logo_yields_no_finding(
    tmp_path: Path, reference_dir: Path
):
    root = tmp_path / "repo"
    root.mkdir()
    draw_logo((12, 6)).save(root / "logo-tiny.png")

    result = scan_images(root, scope(), strategy(reference_dir), image_scope=ImageScope())

    assert not result.findings
    assert result.images_below_minimum == 1
    assert result.images_examined == 0


def test_an_exempted_path_is_assessed_whatever_its_size(
    tmp_path: Path, reference_dir: Path
):
    """The reason the exemption exists: at a raised minimum a favicon would
    otherwise go the way of the spacers, silently, in the same edit."""
    root = tmp_path / "repo"
    root.mkdir()
    # Drawn at size rather than downsampled from the reference: resampling a
    # 240x120 lockup into 24 pixels destroys the signature outright, which is
    # the strategy's own limit and not what this test is about.
    draw_logo((24, 24)).save(root / "favicon.png")
    write_png(root / "assets" / "spacer.png", (16, 16))

    gate = ImageScope(min_dimension=32, always_examine=["favicon*"])
    result = scan_images(root, scope(), strategy(reference_dir), image_scope=gate)

    assert result.images_examined == 1
    assert result.images_below_minimum == 1
    assert [finding.path for finding in result.findings] == ["favicon.png"]


def test_an_exemption_is_matched_on_the_path_or_the_bare_filename(
    tmp_path: Path, reference_dir: Path
):
    root = tmp_path / "repo"
    (root / "wwwroot").mkdir(parents=True)
    draw_logo((24, 24)).save(root / "wwwroot" / "favicon.png")

    gate = ImageScope(min_dimension=32, always_examine=["favicon*"])
    result = scan_images(root, scope(), strategy(reference_dir), image_scope=gate)

    assert result.images_examined == 1
    assert result.images_below_minimum == 0


def test_an_undersized_data_uri_is_ruled_out_against_its_containing_file(
    tmp_path: Path, reference_dir: Path
):
    root = tmp_path / "repo"
    root.mkdir()
    embedded = [
        EmbeddedImage(
            containing_path="index.html", line=12, subtype="png", data=png_bytes((1, 1))
        )
    ]

    result = scan_images(
        root, scope(), strategy(reference_dir), embedded, image_scope=ImageScope()
    )

    assert result.images_below_minimum == 1
    assert not result.issues
    assert result.images_examined == 0


def test_a_zero_minimum_rules_nothing_out(tmp_path: Path, reference_dir: Path):
    root = tmp_path / "repo"
    root.mkdir()
    write_png(root / "assets" / "spacer.png", (2, 2))
    draw_logo().save(root / "logo.png")

    result = scan_images(
        root, scope(), strategy(reference_dir), image_scope=ImageScope(min_dimension=0)
    )

    assert result.images_below_minimum == 0
    assert result.images_examined == 2


def test_findings_above_the_minimum_are_unaffected_by_the_junk_around_them(
    tmp_path: Path, reference_dir: Path
):
    root = tmp_path / "repo"
    (root / "assets").mkdir(parents=True)
    draw_logo().save(root / "logo.png")
    draw_logo((480, 240)).save(root / "assets" / "logo-2x.png")
    baseline = scan_images(
        root, scope(), strategy(reference_dir), image_scope=ImageScope(min_dimension=0)
    )

    for index in range(20):
        write_png(root / "assets" / f"spacer-{index}.png", (1, 1))
    gated = scan_images(root, scope(), strategy(reference_dir), image_scope=ImageScope())

    assert [(f.path, f.matched, f.distance) for f in gated.findings] == [
        (f.path, f.matched, f.distance) for f in baseline.findings
    ]
    # Both copies of the logo match, at whatever size they were stored: the gate
    # decides eligibility, never which reference a candidate matches.
    assert {finding.path for finding in gated.findings} == {
        "logo.png",
        "assets/logo-2x.png",
    }
