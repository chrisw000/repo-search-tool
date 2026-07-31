"""Inputs that could not be read, and what the scan says about them.

A file the scanner could not read must never be indistinguishable from a file
that held nothing. These tests cover the two halves of that: every way an input
can fail to be read is classified by cause, and an input that was never really
read is kept out of the count of images examined.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from brandscan.acquisition.models import RepoTarget
from brandscan.config.model import ReferenceImage, ScanScope
from brandscan.findings import UnreadableCause
from brandscan.images.loader import ImageLoadError, open_image, open_image_bytes
from brandscan.images.strategy import PerceptualHashStrategy
from brandscan.logging_setup import LOGGER_NAME, configure_logging
from brandscan.report.markdown import render_repo_markdown
from brandscan.results import Provenance, RepoResult, RepoStatus
from brandscan.scan.embedded import EmbeddedImage
from brandscan.scan.image_search import scan_images
from tests.conftest import draw_logo

# A valid vector, for the cases that need one good image alongside the bad ones.
GOOD_SVG = (
    b'<?xml version="1.0"?>'
    b'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="120">'
    b'<rect x="19" y="24" width="53" height="72" fill="#0F62FE"/>'
    b"</svg>"
)

# One entry per classified cause, and every shape of emptiness the requirement
# names: no bytes, whitespace, a byte-order mark, a declaration, and comments.
UNREADABLE: dict[str, tuple[bytes, UnreadableCause]] = {
    "zero-byte.png": (b"", UnreadableCause.EMPTY),
    "whitespace.svg": (b"  \n\t\r\n  ", UnreadableCause.EMPTY),
    "byte-order-mark.svg": (b"\xef\xbb\xbf", UnreadableCause.EMPTY),
    "wide-byte-order-mark.svg": (b"\xff\xfe", UnreadableCause.EMPTY),
    "declaration.svg": (b'<?xml version="1.0" encoding="UTF-8"?>\n', UnreadableCause.EMPTY),
    "comment.svg": (b"<!-- artwork pending -->\n", UnreadableCause.EMPTY),
    "doctype.svg": (
        b'<?xml version="1.0"?>\n'
        b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
        b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'
        b"<!-- logo to follow -->\n",
        UnreadableCause.EMPTY,
    ),
    "in-lfs.png": (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:4d7a214614ab2935c943f9e0ff69d22eadbb8f32b1258daaa5e2ca24d17e2393\n"
        b"size 84213\n",
        UnreadableCause.VCS_POINTER,
    ),
    "error-page.png": (
        b"<!DOCTYPE html>\n<html><body><h1>404 Not Found</h1></body></html>\n",
        UnreadableCause.NOT_AN_IMAGE,
    ),
    "prose.svg": (b"The logo lives in the brand portal, not in this repo.\n", UnreadableCause.NOT_AN_IMAGE),
    "truncated.svg": (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="120">'
        b'<rect x="19" y="24"',
        UnreadableCause.RENDERED_BLANK,
    ),
    "corrupt.png": (b"\x89PNG\r\n\x1a\n not actually a png", UnreadableCause.MALFORMED),
    "no-dimensions.svg": (b"<svg><this is not xml", UnreadableCause.MALFORMED),
    # The one input the rasteriser itself complains about, and the reason the
    # relay in `logging_setup` exists: svglib logs "Failed to load input file!"
    # for this and names no file.
    "corrupt.svg": (b"\x00\x01\x02\x03 <svg garbage \xff\xfe\x00", UnreadableCause.MALFORMED),
}


@pytest.fixture
def unreadable_repo(tmp_path: Path) -> Path:
    """A repository holding one of every unreadable input, and one good image."""
    root = tmp_path / "repo"
    (root / "assets").mkdir(parents=True)
    for name, (data, _) in UNREADABLE.items():
        (root / "assets" / name).write_bytes(data)
    return root


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


# --- Classification -------------------------------------------------------


@pytest.mark.parametrize("name", sorted(UNREADABLE))
def test_every_unreadable_input_is_classified_by_cause(tmp_path: Path, name: str):
    data, expected = UNREADABLE[name]
    path = tmp_path / name
    path.write_bytes(data)

    with pytest.raises(ImageLoadError) as raised:
        open_image(path)

    assert raised.value.cause is expected
    # The free-text reason survives alongside the cause: for a malformed file
    # the decoder's own message is the only real evidence.
    assert raised.value.reason


def test_a_placeholder_is_distinguished_from_a_malformed_image(tmp_path: Path):
    placeholder = tmp_path / "logo.svg"
    placeholder.write_bytes(b"<!-- artwork pending -->")
    corrupt = tmp_path / "logo.png"
    corrupt.write_bytes(b"\x89PNG\r\n\x1a\n rubbish")

    with pytest.raises(ImageLoadError) as empty:
        open_image(placeholder)
    with pytest.raises(ImageLoadError) as malformed:
        open_image(corrupt)

    assert empty.value.cause is UnreadableCause.EMPTY
    assert malformed.value.cause is UnreadableCause.MALFORMED
    assert empty.value.cause is not malformed.value.cause
    # The empty one is a skip, not a failure, and says so both ways.
    assert "skipped" in empty.value.reason
    assert "not a defect" in UnreadableCause.EMPTY.remediation
    # The malformed one keeps the decoder's own message: when a file is
    # genuinely puzzling that is the only real evidence.
    assert "could not be decoded" in malformed.value.reason


def test_a_pointer_is_distinguished_because_its_remedy_is_to_fetch(tmp_path: Path):
    pointer = tmp_path / "logo.png"
    pointer.write_bytes(UNREADABLE["in-lfs.png"][0])

    with pytest.raises(ImageLoadError) as raised:
        open_image(pointer)

    assert raised.value.cause is UnreadableCause.VCS_POINTER
    assert "fetch" in raised.value.cause.remediation.lower()


def test_an_empty_input_never_reaches_a_decoder(tmp_path: Path, monkeypatch):
    """The noise disappears at source: a parser never invoked cannot log."""

    def refuse(*args, **kwargs):
        raise AssertionError("a decoder was invoked for an empty input")

    monkeypatch.setattr("brandscan.images.loader.rasterise_svg_bytes", refuse)
    monkeypatch.setattr("PIL.Image.open", refuse)

    for name, data in (("empty.svg", b"<!-- nothing yet -->"), ("empty.png", b"")):
        path = tmp_path / name
        path.write_bytes(data)
        with pytest.raises(ImageLoadError) as raised:
            open_image(path)
        assert raised.value.cause is UnreadableCause.EMPTY


@pytest.mark.parametrize(
    "data,subtype,expected",
    [
        (b"", "png", UnreadableCause.EMPTY),
        (b"<!-- pending -->", "svg+xml", UnreadableCause.EMPTY),
        (b"<html><body>Sign in</body></html>", "png", UnreadableCause.NOT_AN_IMAGE),
        (b"\x89PNG\r\n\x1a\n truncated", "png", UnreadableCause.MALFORMED),
    ],
)
def test_an_inlined_image_is_classified_like_a_file(
    data: bytes, subtype: str, expected: UnreadableCause
):
    with pytest.raises(ImageLoadError) as raised:
        open_image_bytes(data, subtype)
    assert raised.value.cause is expected


# --- Contentless renders --------------------------------------------------


def test_a_truncated_vector_is_not_counted_among_images_examined(
    tmp_path: Path, reference_dir: Path
):
    """Previously rendered as a blank canvas and counted as a successful read."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "truncated.svg").write_bytes(UNREADABLE["truncated.svg"][0])
    draw_logo().save(root / "logo.png")

    result = scan_images(root, scope(), strategy(reference_dir))

    assert result.images_examined == 1
    causes = [issue.cause for issue in result.issues]
    assert causes == [UnreadableCause.RENDERED_BLANK]


def test_a_repository_carrying_only_a_blank_render_does_not_read_as_verified(
    tmp_path: Path, reference_dir: Path
):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "truncated.svg").write_bytes(UNREADABLE["truncated.svg"][0])

    scanned = scan_images(root, scope(), strategy(reference_dir))
    assert not scanned.findings

    markdown = render_repo_markdown(
        _clean_result_with(scanned.issues, scanned.images_examined)
    )

    assert "truncated.svg" in markdown
    assert "unassessed" in markdown
    assert "scanned in full" not in markdown
    assert "**Images examined:** 0" in markdown


def _clean_result_with(issues, images_examined: int) -> RepoResult:
    return RepoResult(
        target=RepoTarget(
            host="github.com",
            org="acme",
            name="widgets",
            default_branch="master",
            clone_url="u",
        ),
        status=RepoStatus.CLEAN,
        provenance=Provenance(
            tool_version="0.1.0", scanned_at="2026-07-31T00:00:00+00:00"
        ),
        issues=list(issues),
        images_examined=images_examined,
    )


# --- Decoder diagnostics --------------------------------------------------


class _Collector(logging.Handler):
    """Stands in for anything that would show a record to the operator."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_decoder_diagnostics_reach_the_run_log_and_nothing_else(
    unreadable_repo: Path, reference_dir: Path, tmp_path: Path, capsys
):
    log_file = tmp_path / "run.jsonl"
    configure_logging(log_file=log_file)
    escaped = _Collector()
    root = logging.getLogger()
    root.addHandler(escaped)

    try:
        result = scan_images(unreadable_repo, scope(), strategy(reference_dir))
    finally:
        root.removeHandler(escaped)
        for handler in logging.getLogger(LOGGER_NAME).handlers:
            handler.close()
        logging.getLogger(LOGGER_NAME).handlers.clear()

    assert len(result.issues) == len(UNREADABLE)

    # Nothing escaped to anything an operator watches.
    assert not [r for r in escaped.records if r.name.split(".")[0] in ("svglib", "reportlab")]
    captured = capsys.readouterr()
    assert "Failed to load input file" not in captured.err + captured.out

    entries = [
        json.loads(line)
        for line in log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    relayed = [entry for entry in entries if entry.get("library", "").startswith("svglib")]
    assert relayed, "the library's own message is evidence and must be kept"
    assert any("Failed to load input file" in entry["message"] for entry in relayed)
    # A message the library could not attribute now names its file.
    assert all(entry["file"] != "unknown" for entry in relayed)
    assert any("corrupt.svg" in entry["file"] for entry in relayed)


def test_every_unreadable_input_in_a_repository_is_recorded_once(
    unreadable_repo: Path, reference_dir: Path
):
    result = scan_images(unreadable_repo, scope(), strategy(reference_dir))

    assert result.images_examined == 0
    recorded = {Path(issue.path).name: issue.cause for issue in result.issues}
    assert recorded == {name: cause for name, (_, cause) in UNREADABLE.items()}


def test_an_inlined_payload_that_fails_is_recorded_against_its_containing_file(
    tmp_path: Path, reference_dir: Path
):
    root = tmp_path / "repo"
    root.mkdir()
    embedded = [
        EmbeddedImage(
            containing_path="index.html",
            line=12,
            subtype="png",
            data=b"<html><body>Sign in</body></html>",
        )
    ]

    result = scan_images(root, scope(), strategy(reference_dir), embedded)

    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.path == "index.html"
    assert issue.line == 12
    assert issue.cause is UnreadableCause.NOT_AN_IMAGE
