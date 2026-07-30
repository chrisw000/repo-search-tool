"""Loading the labelled reference-image set.

Every reference must carry a label naming the brand layout it represents,
because a finding that says "matched a reference image" without saying *which*
is not actionable. An unlabelled reference is a configuration error, not a
reference that quietly gets a filename-shaped label.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from brandscan.config.model import ReferenceImage

REFERENCE_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico", ".svg",
}

LABEL_SIDECAR_NAMES = ("labels.yaml", "labels.yml")


class ReferenceError(Exception):
    """Raised when the reference set cannot be resolved. Names the offender."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def _load_sidecar_labels(directory: Path) -> dict[str, str]:
    for candidate in LABEL_SIDECAR_NAMES:
        sidecar = directory / candidate
        if not sidecar.is_file():
            continue
        try:
            data = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ReferenceError(
                f"reference_images.dir ({candidate})", f"{candidate} is not valid YAML: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ReferenceError(
                f"reference_images.dir ({candidate})",
                f"{candidate} must map each reference image filename to a label",
            )
        return {str(k): str(v) for k, v in data.items()}
    return {}


def _resolve_label(image: Path, labels: dict[str, str]) -> str | None:
    """Look a label up by filename, then by stem. Nothing else counts."""
    for key in (image.name, image.stem):
        if key in labels:
            value = labels[key].strip()
            if value:
                return value
    return None


def load_reference_images(
    directory: Path, configured_labels: dict[str, str] | None = None
) -> list[ReferenceImage]:
    """Collect labelled reference images from a folder.

    Labels come from the configuration's own mapping first, then from a
    `labels.yaml` sidecar in the folder. An image matched by neither fails
    validation and is named in the error.
    """
    if not directory.is_dir():
        raise ReferenceError(
            "reference_images.dir", f"reference image directory not found: {directory}"
        )

    labels: dict[str, str] = dict(_load_sidecar_labels(directory))
    labels.update(configured_labels or {})

    images = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in REFERENCE_SUFFIXES
    )
    if not images:
        raise ReferenceError(
            "reference_images.dir",
            f"no reference images found in {directory}; expected files with one of "
            f"{', '.join(sorted(REFERENCE_SUFFIXES))}",
        )

    references: list[ReferenceImage] = []
    unlabelled: list[str] = []
    for image in images:
        label = _resolve_label(image, labels)
        if label is None:
            unlabelled.append(image.name)
            continue
        references.append(ReferenceImage(path=image, label=label))

    if unlabelled:
        raise ReferenceError(
            "reference_images.labels",
            "reference image has no resolvable label: "
            + ", ".join(unlabelled)
            + f". Add an entry for it under reference_images.labels, or in a "
            f"labels.yaml in {directory}.",
        )

    return references
