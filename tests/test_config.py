"""Configuration: validation, the search-group model, and scope defaults."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from brandscan.config.defaults import (
    BUILD_OUTPUT_DIRS_NOT_EXCLUDED,
    DEFAULT_ALWAYS_EXAMINE_GLOBS,
    DEFAULT_EXCLUDE_DIRS,
)
from brandscan.config.loader import ConfigError, load_config, validate_config
from brandscan.config.model import (
    DEFAULT_MIN_IMAGE_DIMENSION,
    DEFAULT_SIMILARITY_THRESHOLD,
    Severity,
    colour_notation_patterns,
)
from brandscan.config.scalars import load_yaml
from brandscan.scan.walker import matches_any

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


# --- Minimum candidate image size -----------------------------------------


def test_minimum_image_size_defaults_and_seeds_the_favicon_exemptions(tmp_path: Path):
    config = config_from({}, tmp_path)
    assert config.image_scope.min_dimension == DEFAULT_MIN_IMAGE_DIMENSION
    assert config.image_scope.always_examine == DEFAULT_ALWAYS_EXAMINE_GLOBS


def test_a_raised_minimum_still_exempts_favicons_without_a_code_change(tmp_path: Path):
    """The reason the exemption exists: at 15 it is inert, at 32 it is the only
    thing keeping a 16x16 favicon assessable."""
    config = config_from({"image_scope": {"min_dimension": 32}}, tmp_path)
    assert config.image_scope.is_too_small((16, 16))
    assert matches_any("static/favicon.png", config.image_scope.always_examine)


def test_a_configured_minimum_replaces_the_default(tmp_path: Path):
    config = config_from({"image_scope": {"min_dimension": 24}}, tmp_path)
    assert config.image_scope.min_dimension == 24


def test_a_zero_minimum_disables_the_gate(tmp_path: Path):
    config = config_from({"image_scope": {"min_dimension": 0}}, tmp_path)
    assert config.image_scope.min_dimension == 0
    assert not config.image_scope.is_too_small((1, 1))


@pytest.mark.parametrize(
    "value", ["true", "-1", '"15"', "15.5"], ids=["boolean", "negative", "string", "float"]
)
def test_a_bad_minimum_dimension_is_named(value: str, tmp_path: Path):
    """`true` is the same regression risk as the threshold's: a bool is an int,
    so a careless check would admit it as a minimum of 1."""
    with pytest.raises(ConfigError) as excinfo:
        config_from_yaml(YAML_BASE + f"image_scope:\n  min_dimension: {value}\n", tmp_path)
    assert excinfo.value.field == "image_scope.min_dimension"


def test_configured_exemptions_replace_the_seeded_ones(tmp_path: Path):
    config = config_from(
        {"image_scope": {"always_examine": ["assets/sprites/*.png"]}}, tmp_path
    )
    assert config.image_scope.always_examine == ["assets/sprites/*.png"]


def test_an_empty_exemption_list_exempts_nothing(tmp_path: Path):
    config = config_from({"image_scope": {"always_examine": []}}, tmp_path)
    assert config.image_scope.always_examine == []
    assert not matches_any("favicon.ico", config.image_scope.always_examine)


def test_a_non_string_exemption_is_named(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        config_from({"image_scope": {"always_examine": [{"glob": "favicon*"}]}}, tmp_path)
    assert excinfo.value.field == "image_scope.always_examine[0]"


# --- Numeric scalars in string-valued positions ---------------------------
#
# A company number is a bare numeral, so YAML resolves it to an integer. These
# exercise the loader through a real file, because the defect being guarded
# against lives in the parse: PyYAML reads a leading-zero numeral made only of
# octal digits as octal, so the source text is the only trustworthy value.


def config_from_yaml(text: str, tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return load_config(path)


YAML_BASE = """
targets:
  - host: github.com
    org: contoso
brand:
  names: [Contoso]
"""


def test_a_company_number_is_accepted_as_a_bare_numeral(tmp_path: Path):
    config = config_from_yaml(
        YAML_BASE + "  legal:\n    - 3909886\n    - 03909886\n", tmp_path
    )
    patterns = config.group("legal-strings").patterns
    assert "3909886" in patterns
    assert "03909886" in patterns


def test_an_octal_looking_company_number_keeps_its_digits(tmp_path: Path):
    """The case the whole change exists for.

    `07654321` is all octal digits behind a leading zero, so YAML 1.1 reads it
    as octal 2054353. Searching for that instead would report every repository
    carrying the real company number as clean.
    """
    config = config_from_yaml(YAML_BASE + "  legal:\n    - 07654321\n", tmp_path)
    patterns = config.group("legal-strings").patterns
    assert "07654321" in patterns
    assert "2054353" not in patterns


def test_a_numeral_is_admitted_in_a_brand_name(tmp_path: Path):
    config = config_from_yaml("""
targets:
  - host: github.com
    org: contoso
brand:
  names:
    - 0700
""", tmp_path)
    assert "0700" in config.group("brand-names").patterns


def test_a_numeral_is_admitted_in_a_user_defined_group(tmp_path: Path):
    config = config_from_yaml(
        YAML_BASE
        + """
search_groups:
  - name: internal-codes
    patterns:
      - 07654321
""",
        tmp_path,
    )
    assert config.group("internal-codes").patterns == ["07654321"]


def test_a_numeral_is_admitted_in_a_scope_glob(tmp_path: Path):
    config = config_from_yaml(
        YAML_BASE + "scope:\n  exclude_dirs:\n    - 2024\n", tmp_path
    )
    assert config.scope.exclude_dirs == ["2024"]


def test_a_numeral_is_admitted_in_a_repository_name(tmp_path: Path):
    config = config_from_yaml("""
targets:
  - host: github.com
    org: contoso
    repos:
      - 0700
brand:
  names: [Contoso]
""", tmp_path)
    assert config.targets[0].repos == ("0700",)


def test_a_numeral_in_disable_search_groups_reports_the_numeral(tmp_path: Path):
    """Coerced first, then rejected on its own merits — not as a type error."""
    with pytest.raises(ConfigError) as excinfo:
        config_from_yaml(YAML_BASE + "disable_search_groups:\n  - 12345\n", tmp_path)
    assert excinfo.value.field == "disable_search_groups"
    assert "12345" in excinfo.value.message


def test_a_quoted_numeral_is_unchanged(tmp_path: Path):
    quoted = config_from_yaml(YAML_BASE + '  legal:\n    - "07654321"\n', tmp_path)
    bare = config_from_yaml(YAML_BASE + "  legal:\n    - 07654321\n", tmp_path)
    assert quoted.group("legal-strings").patterns == bare.group("legal-strings").patterns


@pytest.mark.parametrize(
    "entry",
    [
        "    - {a: b}",      # a mapping
        "    - [nested]",    # a nested list
        "    -",             # an empty entry
        "    - No",          # YAML's boolean words stay out (design D3)
    ],
    ids=["mapping", "nested-list", "empty", "boolean-word"],
)
def test_a_non_numeric_value_is_still_rejected_by_field(entry: str, tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        config_from_yaml(YAML_BASE + "  legal:\n" + entry + "\n", tmp_path)
    assert excinfo.value.field == "brand.legal[0]"


def test_an_empty_entry_never_becomes_a_match_everything_pattern(tmp_path: Path):
    """An empty pattern would match every file in the estate."""
    with pytest.raises(ConfigError):
        config_from_yaml(YAML_BASE + "  legal:\n    -\n", tmp_path)


# --- Typed fields stay typed ----------------------------------------------


def test_integer_fields_accept_integers(tmp_path: Path):
    config = config_from_yaml(
        YAML_BASE + "similarity_threshold: 5\nscope:\n  max_file_bytes: 1024\n", tmp_path
    )
    assert config.similarity_threshold == 5
    assert config.scope.max_file_bytes == 1024


@pytest.mark.parametrize(
    "line",
    [
        "similarity_threshold: true",
        'similarity_threshold: "5"',
        "similarity_threshold: -1",
    ],
    ids=["boolean", "string", "negative"],
)
def test_a_bad_similarity_threshold_is_still_rejected(line: str, tmp_path: Path):
    """`true` is the specific regression risk: a raw-carrying int subclass
    cannot be a `bool`, so a careless implementation would accept it as 1."""
    with pytest.raises(ConfigError) as excinfo:
        config_from_yaml(YAML_BASE + line + "\n", tmp_path)
    assert excinfo.value.field == "similarity_threshold"


@pytest.mark.parametrize(
    "value", ["true", '"1024"', "0"], ids=["boolean", "string", "zero"]
)
def test_a_bad_max_file_bytes_is_still_rejected(value: str, tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        config_from_yaml(YAML_BASE + f"scope:\n  max_file_bytes: {value}\n", tmp_path)
    assert excinfo.value.field == "scope.max_file_bytes"


def test_boolean_fields_accept_booleans(tmp_path: Path):
    config = config_from_yaml("""
targets:
  - host: github.com
    org: contoso
    include_archived: true
    include_forks: false
brand:
  names: [Contoso]
search_groups:
  - name: brand-names
    case_sensitive: true
""", tmp_path)
    assert config.targets[0].include_archived is True
    assert config.targets[0].include_forks is False
    assert config.group("brand-names").case_sensitive is True


def test_a_non_boolean_in_a_boolean_field_is_still_rejected(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        config_from_yaml("""
targets:
  - host: github.com
    org: contoso
    include_archived: 1
brand:
  names: [Contoso]
""", tmp_path)
    assert excinfo.value.field == "targets[0].include_archived"


def test_a_non_boolean_case_sensitive_is_still_rejected(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        config_from_yaml(
            YAML_BASE + "search_groups:\n  - name: brand-names\n    case_sensitive: 1\n",
            tmp_path,
        )
    assert excinfo.value.field == "search_groups[0].case_sensitive"


def test_a_coerced_colour_still_faces_the_colour_format_rule(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        config_from_yaml("""
targets:
  - host: github.com
    org: contoso
brand:
  names: [Contoso]
  colors:
    - 12345678
""", tmp_path)
    assert excinfo.value.field == "brand.colors[0]"


# --- Reference labels -----------------------------------------------------


def test_a_numeric_sidecar_label_keeps_its_source_text(tmp_path: Path, reference_dir: Path):
    (reference_dir / "labels.yaml").write_text(
        "logo-horizontal.png: 07654321\nlogo-stacked.png: 3909886\n", encoding="utf-8"
    )
    config = config_from({"reference_images": {"dir": str(reference_dir)}}, tmp_path)
    assert config.reference_labels == ["07654321", "3909886"]


def test_a_numeric_configured_label_keeps_its_source_text(
    tmp_path: Path, reference_dir: Path
):
    config = config_from_yaml(
        YAML_BASE
        + f"""
reference_images:
  dir: {reference_dir.as_posix()}
  labels:
    logo-horizontal.png: 07654321
    logo-stacked.png: 07654321
""",
        tmp_path,
    )
    assert config.reference_labels == ["07654321"]


def test_the_shipped_example_configuration_is_valid():
    example = Path(__file__).resolve().parents[1] / "config.example.yaml"
    # Parsed through the real loader, not `yaml.safe_load`: the example shows an
    # unquoted company number, and safe_load would silently reinterpret it.
    data = load_yaml(example.read_text(encoding="utf-8"))
    # The example points at a reference folder that only exists once an
    # operator supplies their own logos, so validate the rest of it.
    data.pop("reference_images", None)
    config = validate_config(data, base_dir=example.parent)
    assert config.group("brand-names").severity is Severity.HIGH
    assert "07654321" in config.group("legal-strings").patterns
