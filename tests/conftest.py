"""Shared fixtures: synthetic logos and throwaway git repositories."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw


def draw_logo(
    size: tuple[int, int] = (240, 120),
    background: tuple[int, int, int] | None = (255, 255, 255),
    foreground: tuple[int, int, int] = (15, 98, 254),
    accent: tuple[int, int, int] = (255, 107, 0),
) -> Image.Image:
    """An asymmetric mark that survives resizing but is not confusable with noise."""
    mode = "RGB" if background is not None else "RGBA"
    fill = background if background is not None else (0, 0, 0, 0)
    image = Image.new(mode, size, fill)
    draw = ImageDraw.Draw(image)
    width, height = size

    def scaled(x: float, y: float) -> tuple[int, int]:
        return int(width * x), int(height * y)

    solid = foreground if mode == "RGB" else (*foreground, 255)
    highlight = accent if mode == "RGB" else (*accent, 255)

    draw.rectangle([scaled(0.08, 0.20), scaled(0.30, 0.80)], fill=solid)
    draw.ellipse([scaled(0.34, 0.28), scaled(0.58, 0.72)], fill=solid)
    draw.polygon(
        [scaled(0.62, 0.75), scaled(0.74, 0.22), scaled(0.90, 0.75)], fill=highlight
    )
    draw.rectangle([scaled(0.62, 0.80), scaled(0.90, 0.88)], fill=solid)
    return image


def pad(image: Image.Image, margin: int, colour=(255, 255, 255)) -> Image.Image:
    """Surround an image with padding, keeping its original colour mode."""
    width, height = image.size
    if image.mode == "RGBA":
        colour = (0, 0, 0, 0)
    canvas = Image.new(image.mode, (width + 2 * margin, height + 2 * margin), colour)
    canvas.paste(image, (margin, margin))
    return canvas


@pytest.fixture
def logo() -> Image.Image:
    return draw_logo()


@pytest.fixture
def reference_dir(tmp_path: Path) -> Path:
    """A labelled reference-image folder with one image per layout."""
    directory = tmp_path / "references"
    directory.mkdir()
    draw_logo((240, 120)).save(directory / "logo-horizontal.png")
    draw_logo((120, 240), foreground=(20, 20, 20)).save(directory / "logo-stacked.png")
    (directory / "labels.yaml").write_text(
        "logo-horizontal.png: horizontal-lockup\nlogo-stacked.png: stacked-lockup\n",
        encoding="utf-8",
    )
    return directory


def git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def make_git_repo(path: Path, origin: str, files: dict[str, str] | None = None) -> Path:
    """Create a committed local repository with a fabricated origin remote."""
    path.mkdir(parents=True, exist_ok=True)
    git(["init", "--initial-branch=master"], cwd=path)
    git(["config", "user.email", "test@example.invalid"], cwd=path)
    git(["config", "user.name", "brandscan tests"], cwd=path)
    git(["remote", "add", "origin", origin], cwd=path)
    for name, content in (files or {"README.md": "hello\n"}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    git(["add", "-A"], cwd=path)
    git(["commit", "-m", "initial"], cwd=path)
    return path
