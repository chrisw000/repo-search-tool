"""Text-pattern search: scope, coverage, and base64-embedded images."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from brandscan.config.defaults import default_scope, seed_default_groups
from brandscan.config.model import ScanScope, SearchGroup, Severity
from brandscan.findings import MatchType
from brandscan.scan.embedded import find_embedded_images
from brandscan.scan.text import scan_text
from brandscan.scan.walker import iter_files
from tests.conftest import draw_logo

VOCABULARY = dict(
    names=["Contoso"],
    fonts=["Contoso Sans"],
    domains=["contoso.com"],
    colors=["#0F62FE"],
    legal=["Contoso Limited"],
)


def groups():
    return seed_default_groups(**VOCABULARY)


def write(root: Path, name: str, content: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def matched_groups(findings, path: str | None = None) -> set[str]:
    return {
        finding.matched
        for finding in findings
        if path is None or finding.path == path
    }


# --- Execution and capture ------------------------------------------------


def test_match_captures_path_line_group_severity_and_context(tmp_path: Path):
    write(tmp_path, "src/app.js", "one\ntwo\nconst vendor = 'Contoso';\nfour\nfive\n")
    result = scan_text(tmp_path, default_scope(), groups())

    finding = next(f for f in result.findings if f.matched == "brand-names")
    assert finding.match_type is MatchType.TEXT
    assert finding.path == "src/app.js"
    assert finding.line == 3
    assert finding.severity is Severity.MEDIUM
    assert "const vendor = 'Contoso';" in finding.context
    assert len(finding.context) == 5


def test_each_occurrence_gets_its_own_line_number(tmp_path: Path):
    write(tmp_path, "notes.md", "Contoso\nunrelated\nContoso again\n")
    result = scan_text(tmp_path, default_scope(), groups())
    lines = sorted(f.line for f in result.findings if f.matched == "brand-names")
    assert lines == [1, 3]


def test_a_group_restricts_its_own_scope_without_affecting_others(tmp_path: Path):
    write(tmp_path, "site.css", "font-family: 'Contoso Sans';\n")
    write(tmp_path, "notes.txt", "font-family: 'Contoso Sans';\n")

    result = scan_text(tmp_path, default_scope(), groups())
    # font-names includes stylesheets only; brand-names has no include globs.
    assert "font-names" in matched_groups(result.findings, "site.css")
    assert "font-names" not in matched_groups(result.findings, "notes.txt")
    assert "brand-names" in matched_groups(result.findings, "notes.txt")


def test_global_scope_excludes_dependency_directories(tmp_path: Path):
    write(tmp_path, "node_modules/pkg/index.js", "Contoso\n")
    write(tmp_path, "src/index.js", "Contoso\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert {f.path for f in result.findings} == {"src/index.js"}


def test_build_output_is_scanned(tmp_path: Path):
    """The carve-out that keeps shipped assets visible."""
    write(tmp_path, "dist/bundle.js", "var brand='Contoso';\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert any(f.path == "dist/bundle.js" for f in result.findings)


def test_binary_files_are_not_searched_as_text(tmp_path: Path):
    (tmp_path / "blob.dat").write_bytes(b"Contoso\x00\x00binary")
    result = scan_text(tmp_path, default_scope(), groups())
    assert result.findings == []


# --- Brand-name coverage, including markup --------------------------------


def test_brand_name_in_image_alt_text(tmp_path: Path):
    write(tmp_path, "index.html", '<img src="a.png" alt="The Contoso logo">\n')
    result = scan_text(tmp_path, default_scope(), groups())
    assert "brand-names" in matched_groups(result.findings, "index.html")


def test_brand_name_in_a_css_class_name(tmp_path: Path):
    write(tmp_path, "site.css", ".contoso-header { color: red; }\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert "brand-names" in matched_groups(result.findings, "site.css")


def test_brand_name_in_a_compound_identifier(tmp_path: Path):
    write(tmp_path, "app.ts", "const contosoHeaderLogo = 1;\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert "brand-names" in matched_groups(result.findings, "app.ts")


def test_brand_name_in_an_svg_title(tmp_path: Path):
    write(tmp_path, "mark.svg", "<svg><title>Contoso</title></svg>\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert "brand-names" in matched_groups(result.findings, "mark.svg")


def test_multi_word_brand_name_survives_identifier_spelling(tmp_path: Path):
    seeded = seed_default_groups(**{**VOCABULARY, "names": ["Contoso Group"]})
    write(tmp_path, "site.css", ".contoso-group-banner {}\n")
    write(tmp_path, "app.js", "const contosoGroup = {};\n")
    result = scan_text(tmp_path, default_scope(), seeded)
    assert {f.path for f in result.findings if f.matched == "brand-names"} == {
        "site.css",
        "app.js",
    }


# --- Font, domain, colour, and legal coverage -----------------------------


def test_font_family_declaration(tmp_path: Path):
    write(tmp_path, "site.css", "body { font-family: 'Contoso Sans', sans-serif; }\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert "font-names" in matched_groups(result.findings, "site.css")


def test_embedded_font_file_reference(tmp_path: Path):
    """A font asset is reported. Which group it lands in is the next test's job."""
    write(tmp_path, "site.css", "src: url('/fonts/cs-regular.woff2');\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert [f.line for f in result.findings if f.path == "site.css"] == [1]


def test_external_font_service_reference(tmp_path: Path):
    write(tmp_path, "index.html", '<link href="https://use.typekit.net/abc.css">\n')
    result = scan_text(tmp_path, default_scope(), groups())
    assert [f.line for f in result.findings if f.path == "index.html"] == [1]


# --- Attributing a font asset to the brand --------------------------------


def font_finding(findings, path: str, group: str):
    return next((f for f in findings if f.path == path and f.matched == group), None)


def test_font_file_named_after_a_brand_font_is_a_brand_finding(tmp_path: Path):
    """One configured font attributes every spelling of the filename."""
    for index, spelling in enumerate(
        ["contoso-sans-regular.woff2", "ContosoSans-Regular.woff2", "contoso_sans.ttf"]
    ):
        write(tmp_path, f"s{index}.css", f"src: url('/fonts/{spelling}');\n")
    result = scan_text(tmp_path, default_scope(), groups())

    for index, spelling in enumerate(
        ["contoso-sans-regular.woff2", "ContosoSans-Regular.woff2", "contoso_sans.ttf"]
    ):
        finding = font_finding(result.findings, f"s{index}.css", "font-references")
        assert finding is not None, spelling
        assert finding.severity is Severity.MEDIUM
        # The excerpt names the asset that tied the reference to the brand.
        assert spelling in finding.excerpt
        # Reported once: never as both a brand finding and an inventory item.
        assert font_finding(result.findings, f"s{index}.css", "unattributed-font-assets") is None


def test_font_file_carrying_no_brand_font_name_is_unattributed(tmp_path: Path):
    write(tmp_path, "site.css", "src: url('/fonts/webfont-regular.woff2');\n")
    result = scan_text(tmp_path, default_scope(), groups())

    inventory = font_finding(result.findings, "site.css", "unattributed-font-assets")
    assert inventory is not None
    assert inventory.severity is Severity.LOW
    assert inventory.severity.weight < Severity.MEDIUM.weight
    assert font_finding(result.findings, "site.css", "font-references") is None


def test_service_link_naming_a_brand_font_attributes_to_the_brand(tmp_path: Path):
    write(
        tmp_path,
        "index.html",
        '<link href="https://fonts.googleapis.com/css?family=Contoso+Sans">\n',
    )
    result = scan_text(tmp_path, default_scope(), groups())

    finding = font_finding(result.findings, "index.html", "font-references")
    assert finding is not None
    assert "family=Contoso+Sans" in finding.excerpt
    assert font_finding(result.findings, "index.html", "unattributed-font-assets") is None


def test_service_link_naming_no_brand_font_is_unattributed(tmp_path: Path):
    write(
        tmp_path,
        "index.html",
        '<link href="https://fonts.googleapis.com/css?family=Roboto">\n',
    )
    result = scan_text(tmp_path, default_scope(), groups())

    assert font_finding(result.findings, "index.html", "unattributed-font-assets") is not None
    assert font_finding(result.findings, "index.html", "font-references") is None


def test_well_known_third_party_font_packages_are_not_inventoried(tmp_path: Path):
    write(tmp_path, "a.css", "src: url('/fonts/glyphicons-halflings-regular.woff2');\n")
    write(tmp_path, "b.css", "src: url('/fonts/fa-regular-400.eot');\n")
    # A vendor-named asset that *does* carry a brand font is still a brand finding.
    write(tmp_path, "c.css", "src: url('/fonts/fa-contoso-sans-400.woff2');\n")
    result = scan_text(tmp_path, default_scope(), groups())

    assert font_finding(result.findings, "a.css", "unattributed-font-assets") is None
    assert font_finding(result.findings, "b.css", "unattributed-font-assets") is None
    assert font_finding(result.findings, "c.css", "font-references") is not None


def test_with_no_brand_fonts_every_font_asset_is_unattributed(tmp_path: Path):
    seeded = seed_default_groups(**{**VOCABULARY, "fonts": []})
    # The attributed group has no patterns at all, so nothing can attribute.
    assert next((g for g in seeded if g.name == "font-references")).patterns == []

    write(tmp_path, "site.css", "src: url('/fonts/contoso-sans-regular.woff2');\n")
    result = scan_text(tmp_path, default_scope(), seeded)
    assert font_finding(result.findings, "site.css", "unattributed-font-assets") is not None


# --- Match-text exclusions ------------------------------------------------


def test_a_match_its_group_excludes_by_text_produces_no_finding(tmp_path: Path):
    group = SearchGroup(
        name="tooling",
        patterns=[r"contoso-\w+"],
        exclude_matches=[r"contoso-sample"],
    )
    write(tmp_path, "a.yml", "run: contoso-sample --now\n")
    result = scan_text(tmp_path, default_scope(), [group])
    assert result.findings == []


def test_one_excluded_match_does_not_suppress_another_on_the_same_line(tmp_path: Path):
    group = SearchGroup(
        name="tooling",
        patterns=[r"contoso-\w+"],
        exclude_matches=[r"contoso-sample"],
    )
    write(tmp_path, "a.yml", "run: contoso-sample then contoso-deploy\n")
    result = scan_text(tmp_path, default_scope(), [group])
    assert [f.excerpt for f in result.findings] == ["contoso-deploy"]


def test_a_vetoed_match_does_not_stop_a_later_pattern_in_the_group(tmp_path: Path):
    """The pattern loop continues past a veto rather than breaking out of it."""
    group = SearchGroup(
        name="tooling",
        patterns=[r"contoso-sample", r"contoso-deploy"],
        exclude_matches=[r"contoso-sample"],
    )
    write(tmp_path, "a.yml", "run: contoso-sample then contoso-deploy\n")
    result = scan_text(tmp_path, default_scope(), [group])
    assert [f.excerpt for f in result.findings] == ["contoso-deploy"]


def test_exclusions_are_local_to_the_group_that_declares_them(tmp_path: Path):
    quiet = SearchGroup(
        name="quiet", patterns=[r"Contoso"], exclude_matches=[r"Contoso"]
    )
    loud = SearchGroup(name="loud", patterns=[r"Contoso"])
    write(tmp_path, "a.md", "Contoso\n")
    result = scan_text(tmp_path, default_scope(), [quiet, loud])
    assert matched_groups(result.findings) == {"loud"}


def configured_groups(overrides: dict, tmp_path: Path):
    """Seeded groups as configuration leaves them — the operator's own lever."""
    from brandscan.config.loader import validate_config

    config = validate_config(
        {"brand": {k: list(v) for k, v in VOCABULARY.items()}, **overrides},
        base_dir=tmp_path,
        require_repository_source=False,
    )
    return config.search_groups


def test_clearing_the_seeded_exclusions_restores_the_full_inventory(tmp_path: Path):
    write(tmp_path, "a.css", "src: url('/fonts/glyphicons-halflings-regular.woff2');\n")
    groups_with = configured_groups(
        {"search_groups": [{"name": "unattributed-font-assets", "exclude_matches": []}]},
        tmp_path,
    )
    result = scan_text(tmp_path, default_scope(), groups_with)
    assert font_finding(result.findings, "a.css", "unattributed-font-assets") is not None


def test_disabling_the_inventory_group_leaves_brand_references_reported(tmp_path: Path):
    write(tmp_path, "a.css", "src: url('/fonts/webfont-regular.woff2');\n")
    write(tmp_path, "b.css", "src: url('/fonts/contoso-sans-regular.woff2');\n")
    groups_without = configured_groups(
        {"disable_search_groups": ["unattributed-font-assets"]}, tmp_path
    )
    result = scan_text(tmp_path, default_scope(), groups_without)

    assert "unattributed-font-assets" not in matched_groups(result.findings)
    assert font_finding(result.findings, "b.css", "font-references") is not None


def test_exclusion_case_sensitivity_follows_the_group(tmp_path: Path):
    write(tmp_path, "a.md", "CONTOSO-SAMPLE\n")

    insensitive = SearchGroup(
        name="insensitive",
        patterns=[r"contoso-\w+"],
        exclude_matches=[r"contoso-sample"],
    )
    sensitive = SearchGroup(
        name="sensitive",
        patterns=[r"CONTOSO-\w+"],
        exclude_matches=[r"contoso-sample"],
        case_sensitive=True,
    )
    result = scan_text(tmp_path, default_scope(), [insensitive, sensitive])
    # The insensitive group vetoes on a case-only difference; the sensitive one
    # does not, so its finding survives.
    assert matched_groups(result.findings) == {"sensitive"}


def test_legacy_domain_and_url(tmp_path: Path):
    write(tmp_path, "links.md", "See https://www.contoso.com/about for details\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert "legacy-domains" in matched_groups(result.findings, "links.md")


def test_brand_colour_in_both_notations(tmp_path: Path):
    write(tmp_path, "a.css", "color: #0F62FE;\n")
    write(tmp_path, "b.css", "color: rgb(15, 98, 254);\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert {f.path for f in result.findings if f.matched == "brand-colours"} == {
        "a.css",
        "b.css",
    }


def test_trademark_notice(tmp_path: Path):
    write(tmp_path, "LICENSE.txt", "Copyright 2019 Contoso Limited. All rights reserved.\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert "legal-strings" in matched_groups(result.findings, "LICENSE.txt")


def test_a_configured_group_matches_with_its_own_name_and_severity(tmp_path: Path):
    custom = SearchGroup(
        name="internal-tooling",
        patterns=[r"contoso-deploy"],
        severity=Severity.LOW,
        include=["*.yml"],
    )
    write(tmp_path, "pipeline.yml", "run: contoso-deploy --now\n")
    result = scan_text(tmp_path, default_scope(), [custom])
    finding = result.findings[0]
    assert finding.matched == "internal-tooling"
    assert finding.severity is Severity.LOW


# --- Base64-embedded images ----------------------------------------------


def png_data_uri(image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def test_embedded_image_is_recovered_with_its_location(tmp_path: Path):
    uri = png_data_uri(draw_logo((64, 32)))
    write(tmp_path, "styles.css", f"a\n.logo {{ background: url('{uri}'); }}\n")
    result = scan_text(tmp_path, default_scope(), groups())

    assert len(result.embedded_images) == 1
    embedded = result.embedded_images[0]
    assert embedded.containing_path == "styles.css"
    assert embedded.line == 2
    assert embedded.subtype == "png"


def test_undecodable_payload_is_recorded_and_the_scan_continues(tmp_path: Path):
    bad = "data:image/png;base64," + "!" * 80
    lines = [f".a {{ background: url('{bad}'); }}", "Contoso"]
    images, failures = find_embedded_images("styles.css", lines)
    assert images == []
    # The payload characters are not valid base64, so nothing is even matched
    # as a data URI; either way, nothing raises.
    assert failures == [] or failures[0][0] == 1

    write(tmp_path, "styles.css", "\n".join(lines) + "\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert any(f.matched == "brand-names" for f in result.findings)


def test_corrupt_base64_payload_is_reported_as_an_issue(tmp_path: Path):
    payload = "A" * 65  # valid alphabet, invalid length
    write(tmp_path, "styles.css", f"background: url('data:image/png;base64,{payload}');\n")
    result = scan_text(tmp_path, default_scope(), groups())
    assert result.embedded_images == []
    assert result.issues and "could not be decoded" in result.issues[0].reason


# --- Walker ---------------------------------------------------------------


def test_include_globs_narrow_the_global_scope(tmp_path: Path):
    write(tmp_path, "a.css", "x")
    write(tmp_path, "b.md", "x")
    scope = ScanScope(exclude_dirs=[], exclude_globs=[], include_globs=["*.css"])
    found = {p.name for p in iter_files(tmp_path, scope)}
    assert found == {"a.css"}
