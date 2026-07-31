"""Configuration: validation, the search-group model, and scope defaults."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from brandscan.config.defaults import BUILD_OUTPUT_DIRS_NOT_EXCLUDED, DEFAULT_EXCLUDE_DIRS
from brandscan.config.loader import ConfigError, load_config, validate_config
from brandscan.config.model import DEFAULT_SIMILARITY_THRESHOLD, Severity, colour_notation_patterns

BASE = {
    "targets": [{"host": "github.com", "org": "contoso"}],
    "brand": {"names": ["Contoso"], "colors": ["#0F62FE"]},
}


def config_from(overrides: dict, tmp_path: Path):
    data = {**BASE, **overrides}
    return validate_config(data, base_dir=tmp_path)


# --- Validation aborts and names the field --------------------------------


def test_missing_target_fields_are_named(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        validate_config({"targets": [{"host": "github.com"}]}, base_dir=tmp_path)
    assert excinfo.value.field == "targets[0].org"


def test_invalid_severity_is_named(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        config_from(
            {"search_groups": [{"name": "brand-names", "severity": "urgent"}]}, tmp_path
        )
    assert excinfo.value.field == "search_groups[0].severity"
    assert "urgent" in excinfo.value.message


def test_invalid_colour_is_named(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        validate_config(
            {**BASE, "brand": {"names": ["Contoso"], "colors": ["cornflower"]}},
            base_dir=tmp_path,
        )
    assert excinfo.value.field == "brand.colors[0]"


def test_invalid_regex_is_named(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        config_from({"search_groups": [{"name": "broken", "patterns": ["(unclosed"]}]}, tmp_path)
    assert "patterns" in excinfo.value.field


def test_no_source_of_repositories_is_named(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        validate_config({"brand": {"names": ["Contoso"]}}, base_dir=tmp_path)
    assert excinfo.value.field == "targets"


def test_a_target_may_name_a_subset_of_repositories(tmp_path: Path):
    config = validate_config(
        {
            **BASE,
            "targets": [
                {
                    "host": "github.com",
                    "org": "contoso",
                    "repos": ["legacy-webforms", "checkout-ui"],
                }
            ],
        },
        base_dir=tmp_path,
    )
    target = config.targets[0]
    assert target.repos == ("legacy-webforms", "checkout-ui")
    assert target.is_narrowed


def test_a_target_without_repos_is_not_narrowed(tmp_path: Path):
    config = config_from({}, tmp_path)
    assert config.targets[0].repos == ()
    assert not config.targets[0].is_narrowed


def test_a_qualified_repo_name_is_rejected_by_field(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        validate_config(
            {
                **BASE,
                "targets": [
                    {"host": "github.com", "org": "contoso", "repos": ["contoso/widgets"]}
                ],
            },
            base_dir=tmp_path,
        )
    assert excinfo.value.field == "targets[0].repos[0]"
    assert "repository name only" in excinfo.value.message


def test_a_duplicate_repo_name_is_rejected_by_field(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        validate_config(
            {
                **BASE,
                "targets": [
                    {"host": "github.com", "org": "contoso", "repos": ["a", "a"]}
                ],
            },
            base_dir=tmp_path,
        )
    assert excinfo.value.field == "targets[0].repos[1]"


def test_a_repository_source_may_be_supplied_later(tmp_path: Path):
    """`--external-root` and `--repo` arrive after the file is read."""
    config = validate_config(
        {"brand": {"names": ["Contoso"]}},
        base_dir=tmp_path,
        require_repository_source=False,
    )
    assert config.targets == []
    assert config.external_repositories == []


def test_valid_configuration_loads(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(BASE), encoding="utf-8")
    config = load_config(path)
    assert [t.label for t in config.targets] == ["github.com/contoso"]


# --- The search-group model ----------------------------------------------


def test_default_groups_are_seeded(tmp_path: Path):
    config = validate_config(
        {
            **BASE,
            "brand": {
                "names": ["Contoso"],
                "fonts": ["Contoso Sans"],
                "domains": ["contoso.com"],
                "colors": ["#0F62FE"],
                "legal": ["Contoso Limited"],
            },
        },
        base_dir=tmp_path,
    )
    assert {group.name for group in config.search_groups} == {
        "brand-names",
        "font-names",
        "font-references",
        "legacy-domains",
        "brand-colours",
        "legal-strings",
    }


def test_a_new_group_is_added_by_configuration_alone(tmp_path: Path):
    config = config_from(
        {
            "search_groups": [
                {
                    "name": "internal-tooling",
                    "patterns": ["contoso-deploy"],
                    "severity": "low",
                    "include": ["*.yml"],
                }
            ]
        },
        tmp_path,
    )
    group = config.group("internal-tooling")
    assert group is not None
    assert group.severity is Severity.LOW
    assert group.include == ["*.yml"]
    # Seeded groups are untouched by the addition.
    assert config.group("brand-names") is not None


def test_a_seeded_group_is_retunable(tmp_path: Path):
    config = config_from({"search_groups": [{"name": "brand-names", "severity": "high"}]}, tmp_path)
    group = config.group("brand-names")
    assert group is not None
    assert group.severity is Severity.HIGH
    # Overriding severity alone leaves the seeded patterns in place.
    assert group.patterns


def test_a_seeded_group_is_removable(tmp_path: Path):
    config = config_from({"disable_search_groups": ["brand-colours"]}, tmp_path)
    assert config.group("brand-colours") is None


def test_disabling_an_unknown_group_is_named(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        config_from({"disable_search_groups": ["nonexistent"]}, tmp_path)
    assert excinfo.value.field == "disable_search_groups"


# --- Colour notations -----------------------------------------------------


def test_colour_expands_to_equivalent_notations():
    import re

    patterns = [re.compile(p, re.IGNORECASE) for p in colour_notation_patterns("#0F62FE")]

    def matches(text: str) -> bool:
        return any(p.search(text) for p in patterns)

    assert matches("color: #0F62FE;")
    assert matches("color: rgb(15, 98, 254);")
    assert matches("color: rgba(15,98,254,0.5);")
    assert matches("color: rgb(15 98 254 / 50%);")
    assert not matches("color: #0F62FF;")


def test_shorthand_hex_is_expanded_only_when_it_exists():
    assert any("#fc0" in p for p in colour_notation_patterns("#FFCC00"))
    assert not any("#0f6\\b" in p for p in colour_notation_patterns("#0F62FE"))


# --- Reference images -----------------------------------------------------


def test_reference_labels_are_loaded(tmp_path: Path, reference_dir: Path):
    config = config_from({"reference_images": {"dir": str(reference_dir)}}, tmp_path)
    assert config.reference_labels == ["horizontal-lockup", "stacked-lockup"]


def test_unlabelled_reference_fails_validation_by_name(tmp_path: Path, reference_dir: Path):
    from tests.conftest import draw_logo

    draw_logo((80, 80)).save(reference_dir / "mystery-mark.png")
    with pytest.raises(ConfigError) as excinfo:
        config_from({"reference_images": {"dir": str(reference_dir)}}, tmp_path)
    assert "mystery-mark.png" in excinfo.value.message


def test_labels_may_come_from_the_configuration(tmp_path: Path, reference_dir: Path):
    from tests.conftest import draw_logo

    draw_logo((80, 80)).save(reference_dir / "icon.png")
    config = config_from(
        {"reference_images": {"dir": str(reference_dir), "labels": {"icon.png": "icon-only"}}},
        tmp_path,
    )
    assert "icon-only" in config.reference_labels


def test_missing_reference_directory_is_named(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        config_from({"reference_images": {"dir": str(tmp_path / "absent")}}, tmp_path)
    assert excinfo.value.field == "reference_images.dir"


# --- Threshold ------------------------------------------------------------


def test_threshold_defaults_and_records_that_it_did(tmp_path: Path):
    config = config_from({}, tmp_path)
    assert config.similarity_threshold == DEFAULT_SIMILARITY_THRESHOLD
    assert config.threshold_was_defaulted is True


def test_configured_threshold_is_marked_as_configured(tmp_path: Path):
    config = config_from({"similarity_threshold": 5}, tmp_path)
    assert config.similarity_threshold == 5
    assert config.threshold_was_defaulted is False


def test_negative_threshold_is_named(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        config_from({"similarity_threshold": -1}, tmp_path)
    assert excinfo.value.field == "similarity_threshold"


# --- Scope defaults -------------------------------------------------------


def test_dependency_directories_are_excluded_by_default(tmp_path: Path):
    config = config_from({}, tmp_path)
    assert "node_modules" in config.scope.exclude_dirs
    assert "vendor" in config.scope.exclude_dirs


def test_build_output_is_not_excluded_by_default(tmp_path: Path):
    """Deployed assets often exist only in build output; excluding it hides them."""
    config = config_from({}, tmp_path)
    for directory in BUILD_OUTPUT_DIRS_NOT_EXCLUDED:
        assert directory not in config.scope.exclude_dirs
    assert not set(BUILD_OUTPUT_DIRS_NOT_EXCLUDED) & set(DEFAULT_EXCLUDE_DIRS)


def test_scope_defaults_are_overridable(tmp_path: Path):
    config = config_from({"scope": {"exclude_dirs": ["dist"]}}, tmp_path)
    assert config.scope.exclude_dirs == ["dist"]


def test_the_shipped_example_configuration_is_valid():
    example = Path(__file__).resolve().parents[1] / "config.example.yaml"
    data = yaml.safe_load(example.read_text(encoding="utf-8"))
    # The example points at a reference folder that only exists once an
    # operator supplies their own logos, so validate the rest of it.
    data.pop("reference_images", None)
    config = validate_config(data, base_dir=example.parent)
    assert config.group("brand-names").severity is Severity.HIGH
