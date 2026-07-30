"""Configuration loading and validation.

Validation runs to completion before anything is acquired. A run over hundreds
of repositories takes hours; discovering a typo in a severity value after the
first clone would waste all of it, so every reachable problem is reported here,
with the offending field named.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from brandscan.config.defaults import default_scope, seed_default_groups
from brandscan.config.model import (
    DEFAULT_SIMILARITY_THRESHOLD,
    Config,
    ExternalRepo,
    ScanScope,
    SearchGroup,
    Severity,
    Target,
    is_hex_colour,
)
from brandscan.config.references import ReferenceError, load_reference_images

BRAND_VOCABULARY_KEYS = ("names", "fonts", "domains", "colors", "legal")


class ConfigError(Exception):
    """A configuration problem, always attributed to a named field."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(field, "must be a mapping")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(field, "must be a list")
    return value


def _string_list(value: Any, field: str) -> list[str]:
    items = _require_list(value, field)
    for index, item in enumerate(items):
        if not isinstance(item, str):
            raise ConfigError(f"{field}[{index}]", "must be a string")
    return [item for item in items]


def _parse_severity(value: Any, field: str) -> Severity:
    if isinstance(value, Severity):
        return value
    if not isinstance(value, str):
        raise ConfigError(field, "must be a string")
    try:
        return Severity(value.strip().lower())
    except ValueError:
        allowed = ", ".join(s.value for s in Severity.ordered())
        raise ConfigError(field, f"must be one of {allowed} (got {value!r})") from None


def _parse_targets(raw: Any) -> list[Target]:
    entries = _require_list(raw, "targets")
    targets: list[Target] = []
    for index, entry in enumerate(entries):
        field = f"targets[{index}]"
        entry = _require_mapping(entry, field)
        host = entry.get("host")
        org = entry.get("org")
        if not isinstance(host, str) or not host.strip():
            raise ConfigError(f"{field}.host", "is required and must be a non-empty string")
        if not isinstance(org, str) or not org.strip():
            raise ConfigError(f"{field}.org", "is required and must be a non-empty string")
        for flag in ("include_archived", "include_forks"):
            if flag in entry and not isinstance(entry[flag], bool):
                raise ConfigError(f"{field}.{flag}", "must be true or false")
        targets.append(
            Target(
                host=host.strip(),
                org=org.strip(),
                include_archived=bool(entry.get("include_archived", False)),
                include_forks=bool(entry.get("include_forks", False)),
            )
        )
    return targets


def _parse_external(raw: Any, base_dir: Path) -> list[ExternalRepo]:
    entries = _require_list(raw, "external_repositories")
    externals: list[ExternalRepo] = []
    for index, entry in enumerate(entries):
        field = f"external_repositories[{index}]"
        entry = _require_mapping(entry, field)
        for key in ("host", "org", "name", "path"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(
                    f"{field}.{key}", "is required and must be a non-empty string"
                )
        path = Path(str(entry["path"])).expanduser()
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        externals.append(
            ExternalRepo(
                host=str(entry["host"]).strip(),
                org=str(entry["org"]).strip(),
                name=str(entry["name"]).strip(),
                path=path,
            )
        )
    return externals


def _parse_group_overrides(raw: Any) -> dict[str, dict[str, Any]]:
    entries = _require_list(raw, "search_groups")
    overrides: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for index, entry in enumerate(entries):
        field = f"search_groups[{index}]"
        entry = _require_mapping(entry, field)
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"{field}.name", "is required and must be a non-empty string")
        name = name.strip()
        if name in overrides:
            raise ConfigError(f"{field}.name", f"duplicate search-group name {name!r}")
        overrides[name] = {"_field": field, **entry}
        order.append(name)
    return overrides


def _apply_group_overrides(
    seeded: list[SearchGroup], overrides: dict[str, dict[str, Any]], disabled: list[str]
) -> list[SearchGroup]:
    """Merge configuration over the seeded groups and append user-defined ones.

    Seeded groups are ordinary groups: configuration can retune any field on
    one, or drop it entirely via `disable_search_groups`.
    """
    by_name = {group.name: group for group in seeded}

    for name in disabled:
        if name not in by_name:
            known = ", ".join(sorted(by_name)) or "(none)"
            raise ConfigError(
                "disable_search_groups",
                f"unknown search-group {name!r}; known groups are {known}",
            )
        by_name.pop(name)

    result: list[SearchGroup] = [g for g in seeded if g.name in by_name]

    for name, raw in overrides.items():
        field = raw["_field"]
        existing = by_name.get(name)
        group = existing or SearchGroup(name=name)

        if "patterns" in raw:
            group.patterns = _string_list(raw["patterns"], f"{field}.patterns")
        if "colors" in raw:
            colors = _string_list(raw["colors"], f"{field}.colors")
            for index, colour in enumerate(colors):
                if not is_hex_colour(colour):
                    raise ConfigError(
                        f"{field}.colors[{index}]",
                        f"must be a hexadecimal colour like #0F62FE (got {colour!r})",
                    )
            group.colors = colors
        if "include" in raw:
            group.include = _string_list(raw["include"], f"{field}.include")
        if "exclude" in raw:
            group.exclude = _string_list(raw["exclude"], f"{field}.exclude")
        if "severity" in raw:
            group.severity = _parse_severity(raw["severity"], f"{field}.severity")
        if "description" in raw:
            group.description = str(raw["description"])
        if "remediation" in raw:
            group.remediation = str(raw["remediation"])
        if "case_sensitive" in raw:
            if not isinstance(raw["case_sensitive"], bool):
                raise ConfigError(f"{field}.case_sensitive", "must be true or false")
            group.case_sensitive = raw["case_sensitive"]

        if not group.patterns and not group.colors:
            raise ConfigError(
                f"{field}.patterns",
                f"search-group {name!r} has no patterns and no colors, so it can "
                "never match; give it patterns or remove it",
            )

        if existing is None:
            result.append(group)

    _validate_patterns_compile(result)
    return result


def _validate_patterns_compile(groups: list[SearchGroup]) -> None:
    import re

    for group in groups:
        for pattern in group.patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ConfigError(
                    f"search_groups[{group.name}].patterns",
                    f"invalid regular expression {pattern!r}: {exc}",
                ) from exc


def _parse_scope(raw: Any) -> ScanScope:
    entry = _require_mapping(raw, "scope")
    scope = default_scope()
    if "exclude_dirs" in entry:
        scope.exclude_dirs = _string_list(entry["exclude_dirs"], "scope.exclude_dirs")
    if "exclude_globs" in entry:
        scope.exclude_globs = _string_list(entry["exclude_globs"], "scope.exclude_globs")
    if "include_globs" in entry:
        scope.include_globs = _string_list(entry["include_globs"], "scope.include_globs")
    if "max_file_bytes" in entry:
        value = entry["max_file_bytes"]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ConfigError("scope.max_file_bytes", "must be a positive integer")
        scope.max_file_bytes = value
    return scope


def validate_config(data: dict[str, Any], base_dir: Path) -> Config:
    """Turn raw configuration data into a validated `Config`.

    Raises `ConfigError` naming the offending field on the first problem found.
    """
    if not isinstance(data, dict):
        raise ConfigError("<root>", "configuration must be a mapping")

    targets = _parse_targets(data.get("targets"))
    externals = _parse_external(data.get("external_repositories"), base_dir)
    if not targets and not externals:
        raise ConfigError(
            "targets",
            "at least one {host, org} target or one external repository is required",
        )

    brand = _require_mapping(data.get("brand"), "brand")
    vocabulary = {
        key: _string_list(brand.get(key), f"brand.{key}") for key in BRAND_VOCABULARY_KEYS
    }
    for index, colour in enumerate(vocabulary["colors"]):
        if not is_hex_colour(colour):
            raise ConfigError(
                f"brand.colors[{index}]",
                f"must be a hexadecimal colour like #0F62FE (got {colour!r})",
            )

    overrides = _parse_group_overrides(data.get("search_groups"))
    disabled = _string_list(data.get("disable_search_groups"), "disable_search_groups")

    seeded = seed_default_groups(**vocabulary)
    # A seeded group whose vocabulary is empty can never match; drop it rather
    # than carrying a group that reports nothing and clutters provenance.
    seeded = [g for g in seeded if g.patterns or g.colors or g.name in overrides]
    groups = _apply_group_overrides(seeded, overrides, disabled)

    references_raw = _require_mapping(data.get("reference_images"), "reference_images")
    reference_dir: Path | None = None
    references = []
    if references_raw.get("dir"):
        reference_dir = Path(str(references_raw["dir"])).expanduser()
        if not reference_dir.is_absolute():
            reference_dir = (base_dir / reference_dir).resolve()
        labels_raw = _require_mapping(references_raw.get("labels"), "reference_images.labels")
        labels = {str(k): str(v) for k, v in labels_raw.items()}
        try:
            references = load_reference_images(reference_dir, labels)
        except ReferenceError as exc:
            raise ConfigError(exc.field, exc.message) from exc

    if not groups and not references:
        raise ConfigError(
            "brand",
            "nothing to search for: configure brand vocabulary, at least one "
            "search-group, or a reference-image directory",
        )

    threshold = data.get("similarity_threshold")
    threshold_was_defaulted = threshold is None
    if threshold_was_defaulted:
        threshold = DEFAULT_SIMILARITY_THRESHOLD
    elif not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 0:
        raise ConfigError("similarity_threshold", "must be a non-negative integer")

    output_dir = Path(str(data.get("output_dir", "brandscan-output"))).expanduser()
    if not output_dir.is_absolute():
        output_dir = (base_dir / output_dir).resolve()

    return Config(
        targets=targets,
        external_repositories=externals,
        search_groups=groups,
        reference_images=references,
        reference_dir=reference_dir,
        similarity_threshold=int(threshold),
        threshold_was_defaulted=threshold_was_defaulted,
        scope=_parse_scope(data.get("scope")),
        output_dir=output_dir,
    )


def load_config(path: Path) -> Config:
    """Read and validate a configuration file."""
    if not path.is_file():
        raise ConfigError("<config>", f"configuration file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError("<config>", f"configuration is not valid YAML: {exc}") from exc
    config = validate_config(data or {}, base_dir=path.parent.resolve())
    config.source_path = path.resolve()
    return config
