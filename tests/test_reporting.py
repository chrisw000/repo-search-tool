"""Per-repository reports and the executive summary."""

from __future__ import annotations

import json
import re
from pathlib import Path

from brandscan.acquisition.models import RepoTarget
from brandscan.config.model import (
    CONFIDENCE_BANDS,
    Config,
    SearchGroup,
    Severity,
    band_for,
    reachable_bands,
)
from brandscan.findings import Finding, MatchType, ScanIssue, UnreadableCause
from brandscan.paths import OutputLayout
from brandscan.report.html import render_summary_html
from brandscan.report.markdown import render_repo_markdown, write_repo_report
from brandscan.report.permalink import blob_permalink
from brandscan.report.summary import (
    build_summary,
    counts_reconcile,
    ranked,
    render_summary,
    summary_dict,
    totals,
    write_summary,
)
from brandscan.results import Provenance, RepoResult, RepoStatus

SHA = "a" * 40


def target(name="widgets", host="github.com", org="contoso") -> RepoTarget:
    return RepoTarget(
        host=host, org=org, name=name, default_branch="master", clone_url="u"
    )


def provenance(**overrides) -> Provenance:
    defaults = dict(
        tool_version="0.1.0",
        scanned_at="2026-07-30T12:00:00+00:00",
        search_groups=["brand-names", "brand-colours"],
        reference_labels=["horizontal-lockup"],
        similarity_threshold=10,
        threshold_was_defaulted=True,
        matching_strategy="perceptual-hash",
        commit_sha=SHA,
        branch="master",
    )
    return Provenance(**{**defaults, **overrides})


def text_finding(**overrides) -> Finding:
    defaults = dict(
        match_type=MatchType.TEXT,
        matched="brand-names",
        path="src/app.css",
        line=12,
        severity=Severity.MEDIUM,
        excerpt="contoso-header",
        context=["a", ".contoso-header {}", "b"],
        remediation="Rename the class.",
        permalink=blob_permalink("github.com", "contoso", "widgets", SHA, "src/app.css", 12),
    )
    return Finding(**{**defaults, **overrides})


def image_finding(**overrides) -> Finding:
    defaults = dict(
        match_type=MatchType.IMAGE,
        matched="horizontal-lockup",
        path="dist/img/header.png",
        severity=Severity.HIGH,
        distance=3,
        remediation="Replace the asset.",
        permalink=blob_permalink(
            "github.com", "contoso", "widgets", SHA, "dist/img/header.png"
        ),
    )
    return Finding(**{**defaults, **overrides})


def result(status=RepoStatus.FINDINGS, findings=None, **overrides) -> RepoResult:
    defaults = dict(
        target=target(),
        status=status,
        provenance=provenance(),
        findings=findings if findings is not None else [image_finding(), text_finding()],
        files_scanned=120,
        images_examined=8,
    )
    return RepoResult(**{**defaults, **overrides})


# --- Permalinks -----------------------------------------------------------


def test_permalink_pins_the_commit_and_line():
    url = blob_permalink("github.com", "contoso", "widgets", SHA, "src/app.css", 12)
    assert url == f"https://github.com/contoso/widgets/blob/{SHA}/src/app.css#L12"


def test_permalink_works_for_an_enterprise_host():
    url = blob_permalink("ghes.example", "platform", "portal", SHA, "a/b.png")
    assert url == f"https://ghes.example/platform/portal/blob/{SHA}/a/b.png"


def test_permalink_never_uses_a_branch_name():
    url = blob_permalink("github.com", "contoso", "widgets", SHA, "x.css", 1)
    assert "master" not in url and SHA in url


def test_permalink_is_empty_without_a_commit():
    assert blob_permalink("github.com", "contoso", "widgets", None, "x.css", 1) == ""


def test_permalink_encodes_awkward_paths():
    url = blob_permalink("github.com", "contoso", "widgets", SHA, "a b/c#d.png")
    assert "a%20b/c%23d.png" in url


# --- Finding content ------------------------------------------------------


def test_a_text_finding_carries_everything_required():
    payload = text_finding().to_dict()
    assert payload["match_type"] == "text"
    assert payload["matched"] == "brand-names"
    assert payload["path"] == "src/app.css"
    assert payload["line"] == 12
    assert payload["severity"] == "medium"
    assert payload["permalink"].endswith("#L12")


def test_an_image_finding_carries_its_distance_and_label():
    payload = image_finding().to_dict()
    assert payload["match_type"] == "image"
    assert payload["matched"] == "horizontal-lockup"
    assert payload["distance"] == 3
    assert payload["permalink"].startswith("https://github.com/contoso/widgets/blob/")


# --- Report bodies --------------------------------------------------------


def test_findings_are_presented_as_grouped_fix_instructions():
    markdown = render_repo_markdown(result())
    assert "## What to change" in markdown
    # Grouped into tasks, image first because it is the heavier severity.
    assert markdown.index("`horizontal-lockup`") < markdown.index("`brand-names`")
    assert "**What to do:** Replace the asset." in markdown
    assert "**What to do:** Rename the class." in markdown
    assert "src/app.css" in markdown


def test_occurrences_of_one_thing_collapse_into_a_single_task():
    findings = [text_finding(line=n) for n in (3, 9, 41)]
    markdown = render_repo_markdown(result(findings=findings))
    assert "1 remediation task(s)" in markdown
    assert markdown.count("### 1.") == 1
    for line in (3, 9, 41):
        assert f"line {line}" in markdown


def test_a_clean_repository_says_so_explicitly():
    markdown = render_repo_markdown(result(status=RepoStatus.CLEAN, findings=[]))
    assert "clean" in markdown.lower()
    assert "no remediation is required" in markdown.lower()


def test_a_skipped_repository_is_never_presented_as_clean():
    markdown = render_repo_markdown(
        result(
            status=RepoStatus.SKIPPED,
            findings=[],
            reason="external clone has uncommitted modifications",
        )
    )
    assert "SKIPPED" in markdown
    assert "uncommitted modifications" in markdown
    assert "It is **not** clean" in markdown


def test_a_failed_repository_states_its_reason():
    markdown = render_repo_markdown(
        result(status=RepoStatus.FAILED, findings=[], reason="clone failed: HTTP 404")
    )
    assert "FAILED" in markdown
    assert "HTTP 404" in markdown
    assert "not** clean" in markdown


def test_unreadable_files_are_surfaced_rather_than_swallowed():
    markdown = render_repo_markdown(
        result(issues=[ScanIssue(path="a/broken.svg", reason="could not be parsed")])
    )
    assert "Files that could not be read" in markdown
    assert "a/broken.svg" in markdown
    assert "unassessed rather than clean" in markdown


def unread(path: str, cause: UnreadableCause) -> ScanIssue:
    return ScanIssue(path=path, reason=f"image is {cause.value}", cause=cause)


MIXED_ISSUES = [
    unread("assets/logo.svg", UnreadableCause.EMPTY),
    unread("assets/hero.png", UnreadableCause.VCS_POINTER),
    unread("dist/img/mark.png", UnreadableCause.MALFORMED),
]


def test_unread_inputs_are_distinguished_by_cause_with_their_remedies():
    """Three symptoms of the same shape and three unrelated remedies.

    Presented as one flat list they read as one undifferentiated defect, which
    is how a reader learns to skip the section.
    """
    markdown = render_repo_markdown(result(issues=MIXED_ISSUES))

    for cause in (
        UnreadableCause.EMPTY,
        UnreadableCause.VCS_POINTER,
        UnreadableCause.MALFORMED,
    ):
        assert f"### {cause.heading}" in markdown
        assert cause.remediation in markdown

    # Each remedy is a different instruction, not the same one three times.
    assert "git lfs pull" in markdown
    assert markdown.index("Content never fetched") != markdown.index("Empty placeholders")


def test_the_sidecar_carries_the_same_classification(tmp_path: Path):
    layout = OutputLayout(root=tmp_path, run_dir=tmp_path / "run")
    written = result(issues=MIXED_ISSUES)
    markdown_path = layout.report_markdown("github.com", "contoso", "widgets")
    json_path = layout.report_json("github.com", "contoso", "widgets")
    write_repo_report(written, markdown_path, json_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    recorded = {entry["path"]: entry["cause"] for entry in payload["issues"]}
    assert recorded == {issue.path: issue.cause.value for issue in MIXED_ISSUES}
    # Neither form holds an unread input the other lacks.
    for path in recorded:
        assert path in markdown
    assert markdown.count("- `") >= len(MIXED_ISSUES)


def test_an_issue_survives_the_json_round_trip_with_its_cause():
    issue = ScanIssue(
        path="a/hero.png",
        reason="image is a version-control pointer",
        line=4,
        cause=UnreadableCause.VCS_POINTER,
    )
    restored = ScanIssue.from_dict(issue.to_dict())
    assert restored == issue
    assert restored.cause is UnreadableCause.VCS_POINTER
    assert restored.remediation == UnreadableCause.VCS_POINTER.remediation


def test_an_issue_without_a_cause_still_round_trips():
    issue = ScanIssue(path="a/b.png", reason="unclassified")
    assert ScanIssue.from_dict(issue.to_dict()) == issue


def test_a_clean_repository_with_unread_inputs_is_not_presented_as_verified():
    markdown = render_repo_markdown(
        result(status=RepoStatus.CLEAN, findings=[], issues=MIXED_ISSUES)
    )
    # Clean on findings...
    assert "No text-pattern or image match was found in the content this scan" in markdown
    # ...but never described as verified in full.
    assert "scanned in full" not in markdown
    assert "clean on findings, not verified in full" in markdown
    assert "were **not** assessed" in markdown
    for issue in MIXED_ISSUES:
        assert issue.path in markdown


def test_context_containing_a_fence_does_not_break_the_report():
    finding = text_finding(context=["```", "Contoso", "```"])
    markdown = render_repo_markdown(result(findings=[finding]))
    assert "````" in markdown


# --- Provenance -----------------------------------------------------------


def test_provenance_records_the_conditions_of_the_scan():
    markdown = render_repo_markdown(result())
    for expected in (
        "0.1.0",
        "2026-07-30T12:00:00+00:00",
        SHA,
        "master",
        "perceptual-hash",
        "`brand-names`",
        "`horizontal-lockup`",
    ):
        assert expected in markdown
    assert "10 (default)" in markdown


def test_provenance_marks_a_configured_threshold_as_configured():
    markdown = render_repo_markdown(
        result(provenance=provenance(similarity_threshold=5, threshold_was_defaulted=False))
    )
    assert "5 (configured)" in markdown


# --- The two forms agree --------------------------------------------------


def test_the_sidecar_omits_no_finding(tmp_path: Path):
    outcome = result(findings=[image_finding(), text_finding(line=1), text_finding(line=2)])
    markdown_path = tmp_path / "report.md"
    json_path = tmp_path / "report.json"
    write_repo_report(outcome, markdown_path, json_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(payload["findings"]) == 3
    assert payload["counts"]["findings"] == 3
    assert payload["status"] == "findings"
    for finding in payload["findings"]:
        assert finding["path"] in markdown_path.read_text(encoding="utf-8")


def test_a_result_round_trips_through_its_sidecar():
    original = result()
    restored = RepoResult.from_dict(original.to_dict(), original.target)
    assert restored.status is original.status
    assert [f.to_dict() for f in restored.findings] == [
        f.to_dict() for f in original.findings
    ]
    assert restored.provenance.to_dict() == original.provenance.to_dict()


# --- Collision-safe layout ------------------------------------------------


def test_same_name_on_two_hosts_gets_two_reports(tmp_path: Path):
    layout = OutputLayout(root=tmp_path, run_dir=tmp_path / "run")
    first = layout.report_markdown("github.com", "contoso", "portal")
    second = layout.report_markdown("ghes.example", "contoso", "portal")
    assert first != second


def test_same_name_in_two_organisations_gets_two_reports(tmp_path: Path):
    layout = OutputLayout(root=tmp_path, run_dir=tmp_path / "run")
    first = layout.report_markdown("github.com", "contoso", "portal")
    second = layout.report_markdown("github.com", "fabrikam", "portal")
    assert first != second


# --- Executive summary ----------------------------------------------------


def summary_set() -> list[RepoResult]:
    heavy = result(target=target("heavy"), findings=[image_finding()])
    noisy = result(
        target=target("noisy"),
        findings=[
            text_finding(matched="brand-colours", severity=Severity.LOW, line=n)
            for n in range(30)
        ],
    )
    clean = result(target=target("clean"), status=RepoStatus.CLEAN, findings=[])
    skipped = result(
        target=target("skipped"),
        status=RepoStatus.SKIPPED,
        findings=[],
        reason="uncommitted modifications",
    )
    failed = result(
        target=target("failed"), status=RepoStatus.FAILED, findings=[], reason="HTTP 404"
    )
    for entry in (heavy, noisy, clean, skipped, failed):
        entry.report_path = f"reports/github.com/contoso/{entry.target.name}/report.md"
    return [heavy, noisy, clean, skipped, failed]


def summary_config(**overrides) -> Config:
    """The configuration the summary set was produced under."""
    defaults = dict(
        search_groups=[
            SearchGroup(name="brand-names", severity=Severity.MEDIUM),
            SearchGroup(name="brand-colours", severity=Severity.LOW),
        ],
        similarity_threshold=10,
    )
    return Config(**{**defaults, **overrides})


def model(results=None, run_errors=(), config=None):
    return build_summary(
        summary_set() if results is None else results,
        list(run_errors),
        config or summary_config(),
    )


def row(summary, matched: str):
    return next(entry for entry in summary.by_match if entry.matched == matched)


def test_totals_cover_every_category_and_reconcile():
    counts = totals(summary_set())
    assert counts == {
        "targeted": 5,
        "scanned": 3,
        "clean": 1,
        "with_findings": 2,
        "skipped": 1,
        "failed": 1,
        "findings": 31,
    }
    assert counts_reconcile(counts)


def test_severity_outweighs_raw_count_in_the_ranking():
    order = [r.target.name for r in ranked(summary_set())]
    assert order == ["heavy", "noisy"]


def test_clean_repositories_do_not_occupy_the_ranked_list():
    names = {r.target.name for r in ranked(summary_set())}
    assert "clean" not in names
    assert totals(summary_set())["clean"] == 1


def test_summary_breaks_down_by_match_and_by_severity():
    payload = summary_dict(model())
    lockup = payload["by_match"]["horizontal-lockup"]
    assert lockup["kind"] == "image"
    assert lockup["findings"] == 1
    assert lockup["repositories"] == 1
    assert payload["by_match"]["brand-colours"]["findings"] == 30
    assert payload["by_severity"] == {"high": 1, "medium": 0, "low": 30}


def test_summary_links_through_to_every_repository():
    markdown = render_summary(model())
    for name in ("heavy", "noisy", "skipped", "failed"):
        assert f"reports/github.com/contoso/{name}/report.md" in markdown


def test_summary_shows_skipped_repositories_with_their_reason():
    markdown = render_summary(model())
    assert "## Not scanned" in markdown
    assert "uncommitted modifications" in markdown
    assert "HTTP 404" in markdown


def test_summary_states_that_the_counts_reconcile():
    markdown = render_summary(model())
    assert "Every repository is accounted for" in markdown


def test_summary_warns_when_counts_do_not_reconcile():
    assert not counts_reconcile({"targeted": 6, "clean": 1, "with_findings": 2, "skipped": 1, "failed": 1})


# --- Likeness confidence bands --------------------------------------------


def images_at(*distances: int) -> RepoResult:
    return result(
        target=target("logos"),
        findings=[image_finding(distance=d, path=f"img/{d}.png") for d in distances],
    )


def band_names(summary, matched="horizontal-lockup") -> list[str]:
    return [entry.band.name for entry in row(summary, matched).bands]


def band_counts(summary, matched="horizontal-lockup") -> dict[str, int]:
    return {entry.band.name: entry.findings for entry in row(summary, matched).bands}


def test_the_ladder_puts_each_distance_in_one_band():
    expected = {
        0: "very high",
        2: "very high",
        3: "high",
        5: "high",
        6: "medium",
        8: "medium",
        9: "low",
        12: "low",
        13: "very low",
        40: "very low",
    }
    for distance, name in expected.items():
        assert band_for(distance).name == name, distance


def test_the_ladder_leaves_no_distance_unbanded():
    for distance in range(0, 65):
        assert band_for(distance) is not None


def test_image_findings_are_counted_into_their_bands():
    summary = model(results=[images_at(0, 1, 4, 7, 9)])
    assert band_counts(summary) == {"very high": 2, "high": 1, "medium": 1, "low": 1}


def test_the_closest_match_lands_in_the_most_confident_band():
    summary = model(results=[images_at(0)])
    assert band_counts(summary)["very high"] == 1
    assert band_names(summary)[0] == "very high"


def test_a_band_beyond_the_threshold_is_omitted():
    """At the default threshold no finding can reach 13, so the band is noise."""
    summary = model(results=[images_at(1, 9)])
    assert "very low" not in band_names(summary)


def test_a_reachable_band_is_shown_even_when_empty():
    """`low: 0` at threshold 10 says every match was a solid one."""
    summary = model(results=[images_at(1)])
    assert band_counts(summary) == {"very high": 1, "high": 0, "medium": 0, "low": 0}


def test_raising_the_threshold_brings_the_last_band_back():
    summary = model(
        results=[images_at(1, 14)], config=summary_config(similarity_threshold=20)
    )
    assert band_names(summary)[-1] == "very low"
    assert band_counts(summary)["very low"] == 1


def test_reachable_bands_are_ordered_most_confident_first():
    assert [band.name for band in reachable_bands(64)] == [
        band.name for band in CONFIDENCE_BANDS
    ]
    assert [band.name for band in reachable_bands(10)] == [
        "very high",
        "high",
        "medium",
        "low",
    ]


def test_the_summary_states_the_threshold_and_what_each_band_means():
    markdown = render_summary(model(results=[images_at(1)]))
    html = render_summary_html(model(results=[images_at(1)]))
    for document in (markdown, html):
        assert "0–2" in document
        assert "9–12" in document
        assert "10" in document
        assert "very high" in document


# --- Configured severity in the breakdown ---------------------------------


def test_each_search_group_carries_its_configured_severity():
    summary = model()
    assert row(summary, "brand-colours").severity_label == "low"
    heavier = model(
        results=[
            result(
                target=target("heavy"),
                findings=[text_finding(matched="brand-names", severity=Severity.HIGH)],
            )
        ]
    )
    assert row(heavier, "brand-names").severity_label == "high"


def test_a_reference_label_carries_the_severity_image_findings_carry():
    assert row(model(), "horizontal-lockup").severity_label == "high"


def test_the_rendered_breakdown_shows_each_row_severity():
    summary = model()
    for document in (render_summary(summary), render_summary_html(summary)):
        table = document[document.index("Findings by search-group") :]
        assert "low" in table
        assert "high" in table


# --- The values that matched ----------------------------------------------


def spellings(*excerpts: str) -> RepoResult:
    return result(
        target=target("spellings"),
        findings=[
            text_finding(matched="brand-names", excerpt=excerpt, line=index + 1)
            for index, excerpt in enumerate(excerpts)
        ],
    )


def values_of(summary, matched="brand-names") -> list[tuple[str, int]]:
    return [(entry.value, entry.findings) for entry in row(summary, matched).values]


def test_a_case_insensitive_group_folds_its_spellings_into_one_value():
    summary = model(results=[spellings("OldBrand", "OLDBRAND", "OldBrand", "oldbrand")])
    assert values_of(summary) == [("OldBrand", 4)]


def test_the_folded_value_displays_its_most_frequent_spelling():
    summary = model(results=[spellings("OLDBRAND", "OldBrand", "OldBrand")])
    assert values_of(summary)[0][0] == "OldBrand"


def test_a_case_sensitive_group_keeps_its_spellings_apart():
    summary = model(
        results=[spellings("OldBrand", "OLDBRAND", "OldBrand")],
        config=summary_config(
            search_groups=[
                SearchGroup(name="brand-names", severity=Severity.HIGH, case_sensitive=True)
            ]
        ),
    )
    assert values_of(summary) == [("OldBrand", 2), ("OLDBRAND", 1)]


def test_matched_values_are_ordered_most_frequent_first():
    summary = model(results=[spellings("rare", "common", "common", "common", "rare")])
    assert [value for value, _ in values_of(summary)] == ["common", "rare"]


def crowded(distinct: int) -> RepoResult:
    """One value at every frequency, so the ordering of the cap is checkable."""
    findings = []
    for index in range(distinct):
        for occurrence in range(distinct - index):
            findings.append(
                text_finding(
                    matched="brand-names",
                    excerpt=f"value-{index:02d}",
                    line=len(findings) + 1,
                )
            )
    return result(target=target("crowded"), findings=findings)


def test_the_rendered_documents_cap_the_values_and_say_how_many_were_omitted():
    summary = model(results=[crowded(15)])
    shown, omitted = row(summary, "brand-names").top_values()
    assert len(shown) == 10
    assert omitted == 5
    assert [value.value for value in shown[:3]] == ["value-00", "value-01", "value-02"]

    for document in (render_summary(summary), render_summary_html(summary)):
        assert "value-00" in document
        assert "5 more" in document
        assert "value-14" not in document


def test_the_sidecar_carries_more_values_than_the_documents_show():
    summary = model(results=[crowded(15)])
    values = summary_dict(summary)["by_match"]["brand-names"]["values"]
    assert len(values) == 15
    assert values[0] == {"value": "value-00", "findings": 15}


# --- Repository content is never trusted ----------------------------------


AWKWARD = "Old | Brand <script>alert(1)</script>"


def test_a_pipe_in_a_matched_value_does_not_break_the_markdown_table():
    markdown = render_summary(model(results=[spellings(AWKWARD)]))
    rows = [line for line in markdown.splitlines() if "Old " in line]
    assert rows, markdown
    for line in rows:
        assert "\\|" in line
        # Split on unescaped pipes only: the row must still have four columns.
        assert len(re.split(r"(?<!\\)\|", line)) == 6


def test_markup_in_a_matched_value_is_escaped_in_the_html():
    html = render_summary_html(model(results=[spellings(AWKWARD)]))
    assert "&lt;script&gt;" in html
    assert "<script>alert" not in html


def test_a_skip_reason_is_escaped_in_the_html():
    summary = model(
        results=[
            result(
                target=target("skipped"),
                status=RepoStatus.SKIPPED,
                findings=[],
                reason="<b>dirty</b> & unread",
            )
        ]
    )
    html = render_summary_html(summary)
    assert "&lt;b&gt;dirty&lt;/b&gt; &amp; unread" in html
    assert "<b>dirty</b>" not in html


# --- The HTML rendering ---------------------------------------------------


def test_the_html_summary_fetches_nothing():
    html = render_summary_html(model())
    for external in ("<link", 'src="', "@import", "http://", "https://", "url("):
        assert external not in html, external


def test_the_html_summary_is_complete_without_its_script():
    """Sorting is an enhancement; every row must be in the markup already."""
    html = render_summary_html(model())
    markup = html[: html.index("<script")] if "<script" in html else html
    for name in ("heavy", "noisy", "skipped", "failed"):
        assert f"reports/github.com/contoso/{name}/report.md" in markup


def test_severity_and_confidence_are_readable_without_colour():
    summary = model(results=[images_at(1), *summary_set()])
    html = render_summary_html(summary)
    # Every band and severity names itself in text, not only in a colour class.
    for word in ("very high", "high", "medium", "low"):
        assert f">{word}<" in html


def test_the_html_links_through_to_every_repository():
    html = render_summary_html(model())
    for name in ("heavy", "noisy", "skipped", "failed"):
        assert f'href="reports/github.com/contoso/{name}/report.md"' in html


def test_the_sidecar_agrees_with_the_rendered_documents():
    summary = model(results=[images_at(0, 4, 9), *summary_set()])
    payload = summary_dict(summary)
    markdown = render_summary(summary)
    html = render_summary_html(summary)

    assert payload["similarity_threshold"] == summary.similarity_threshold
    assert [band["name"] for band in payload["confidence_bands"]] == [
        band.name for band in summary.bands
    ]
    for name, entry in payload["by_match"].items():
        recorded = row(summary, name)
        assert entry["findings"] == recorded.findings
        assert entry["severity"] == recorded.severity_label
        assert [band["findings"] for band in entry["bands"]] == [
            band.findings for band in recorded.bands
        ]
        for document in (markdown, html):
            assert name in document
        for value in entry["values"][:10]:
            assert value["value"] in markdown


def test_all_three_forms_are_written(tmp_path: Path):
    layout = OutputLayout(root=tmp_path, run_dir=tmp_path / "run")
    write_summary(
        summary_set(),
        [],
        summary_config(),
        layout.summary_file,
        layout.summary_json_file,
        layout.summary_html_file,
    )
    assert layout.summary_file.is_file()
    assert layout.summary_json_file.is_file()
    assert layout.summary_html_file.is_file()
    assert layout.summary_html_file.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_the_two_renderings_carry_the_same_run():
    """Neither form may be a subset of the other."""
    summary = model(results=[images_at(0, 4, 9), *summary_set()])
    markdown = render_summary(summary)
    html = render_summary_html(summary)

    for document in (markdown, html):
        for key in ("targeted", "scanned", "clean", "with_findings", "skipped", "failed"):
            assert str(summary.totals[key]) in document
        for entry in summary.ranked:
            assert entry.slug in document
            assert entry.report_path in document
        for entry in summary.by_match:
            assert entry.matched in document
            assert entry.severity_label in document
            for value in entry.top_values()[0]:
                assert value.value in document
            for band in entry.bands:
                assert band.band.name in document
        for entry in summary.not_scanned:
            assert entry.slug in document
            assert entry.reason in document
