"""Per-repository reports and the executive summary."""

from __future__ import annotations

import json
from pathlib import Path

from brandscan.acquisition.models import RepoTarget
from brandscan.config.model import Severity
from brandscan.findings import Finding, MatchType, ScanIssue, UnreadableCause
from brandscan.paths import OutputLayout
from brandscan.report.markdown import render_repo_markdown, write_repo_report
from brandscan.report.permalink import blob_permalink
from brandscan.report.summary import (
    counts_reconcile,
    ranked,
    render_summary,
    summary_dict,
    totals,
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
    layout = OutputLayout(tmp_path)
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
    layout = OutputLayout(root=tmp_path)
    first = layout.report_markdown("github.com", "contoso", "portal")
    second = layout.report_markdown("ghes.example", "contoso", "portal")
    assert first != second


def test_same_name_in_two_organisations_gets_two_reports(tmp_path: Path):
    layout = OutputLayout(root=tmp_path)
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
    payload = summary_dict(summary_set(), [])
    assert payload["by_match"]["horizontal-lockup"] == {
        "kind": "image",
        "findings": 1,
        "repositories": 1,
    }
    assert payload["by_match"]["brand-colours"]["findings"] == 30
    assert payload["by_severity"] == {"high": 1, "medium": 0, "low": 30}


def test_summary_links_through_to_every_repository():
    markdown = render_summary(summary_set(), [])
    for name in ("heavy", "noisy", "skipped", "failed"):
        assert f"reports/github.com/contoso/{name}/report.md" in markdown


def test_summary_shows_skipped_repositories_with_their_reason():
    markdown = render_summary(summary_set(), [])
    assert "## Not scanned" in markdown
    assert "uncommitted modifications" in markdown
    assert "HTTP 404" in markdown


def test_summary_states_that_the_counts_reconcile():
    markdown = render_summary(summary_set(), [])
    assert "Every repository is accounted for" in markdown


def test_summary_warns_when_counts_do_not_reconcile():
    assert not counts_reconcile({"targeted": 6, "clean": 1, "with_findings": 2, "skipped": 1, "failed": 1})
