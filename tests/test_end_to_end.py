"""A whole run over a fixture estate.

Everything here goes through the external-clone path, which is exactly the
posture that must never modify what it reads — so the fixtures double as the
non-destructiveness check.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pytest
import yaml

from brandscan.cli import main
from brandscan.config.loader import validate_config
from brandscan.paths import OutputLayout, discover_runs, select_layout
from brandscan.results import RepoStatus
from brandscan.run import execute_run
from brandscan.run_record import RunRecord
from tests.conftest import draw_logo, git, make_git_repo

HOST = "github.com"
ORG = "contoso"


def data_uri(image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


@pytest.fixture
def estate(tmp_path: Path, reference_dir: Path):
    """Five repositories standing in for the real validation set."""
    work = tmp_path / "work"

    # Findings of both kinds, including one inside checked-in build output.
    widgets = make_git_repo(
        work / "widgets",
        f"https://{HOST}/{ORG}/widgets.git",
        {
            "src/site.css": ".contoso-header { color: #0F62FE; }\n",
            "src/index.html": '<img src="logo.png" alt="Contoso logo">\n',
            "node_modules/dep/index.js": "Contoso everywhere\n",
        },
    )
    build_output = widgets / "dist"
    build_output.mkdir(parents=True, exist_ok=True)
    draw_logo((240, 120)).save(build_output / "header.png")
    (build_output / "inline.css").write_text(
        f".mark {{ background: url('{data_uri(draw_logo((120, 60)))}'); }}\n",
        encoding="utf-8",
    )
    git(["add", "-A"], cwd=widgets)
    git(["commit", "-m", "assets"], cwd=widgets)

    pristine = make_git_repo(
        work / "pristine",
        f"https://{HOST}/{ORG}/pristine.git",
        {"README.md": "Nothing to see here.\n"},
    )

    dirty = make_git_repo(
        work / "dirty",
        f"https://{HOST}/{ORG}/dirty.git",
        {"a.txt": "committed content\n"},
    )
    (dirty / "a.txt").write_text("UNCOMMITTED WORK\n", encoding="utf-8")
    (dirty / "untracked.md").write_text("scratch notes\n", encoding="utf-8")

    # A legacy repository on a non-`main` default branch.
    legacy = make_git_repo(
        work / "legacy",
        f"https://{HOST}/{ORG}/legacy.git",
        {"Default.aspx": '<asp:Label Text="Contoso Limited" />\n'},
    )

    config = validate_config(
        {
            "brand": {
                "names": ["Contoso"],
                "colors": ["#0F62FE"],
                "legal": ["Contoso Limited"],
            },
            "reference_images": {"dir": str(reference_dir)},
            "external_repositories": [
                {"host": HOST, "org": ORG, "name": name, "path": str(path)}
                for name, path in (
                    ("widgets", widgets),
                    ("pristine", pristine),
                    ("dirty", dirty),
                    ("legacy", legacy),
                    ("absent", work / "does-not-exist"),
                )
            ],
        },
        base_dir=tmp_path,
    )
    config.output_dir = tmp_path / "out"
    return config, {"widgets": widgets, "dirty": dirty, "pristine": pristine}


def run(config, resume=True, refresh=False, layout=None):
    """One invocation's worth of run, choosing its run directory as the CLI does.

    Passing `layout` re-enters a run directory outright, which is what
    `--run-id` does.
    """
    if layout is None:
        layout = select_layout(config.output_dir, force_new=not resume or refresh)
    return execute_run(config, layout, resume=resume, refresh=refresh), layout


def latest_layout(root: Path) -> OutputLayout:
    """The run directory the most recent invocation wrote to."""
    run_dir, _ = discover_runs(root)[0]
    return OutputLayout(root=root, run_dir=run_dir)


# --- The run as a whole ---------------------------------------------------


def test_every_outcome_is_represented_and_the_totals_reconcile(estate):
    config, _ = estate
    outcome, _ = run(config)

    statuses = {r.target.name: r.status for r in outcome.results}
    assert statuses["widgets"] is RepoStatus.FINDINGS
    assert statuses["legacy"] is RepoStatus.FINDINGS
    assert statuses["pristine"] is RepoStatus.CLEAN
    assert statuses["dirty"] is RepoStatus.SKIPPED
    assert statuses["absent"] is RepoStatus.FAILED

    counts = outcome.totals
    assert counts["targeted"] == 5
    assert counts["clean"] + counts["with_findings"] + counts["skipped"] + counts[
        "failed"
    ] == counts["targeted"]


def test_one_failed_repository_does_not_end_the_run(estate):
    """The failure is recorded against its own repository and nothing else."""
    config, _ = estate
    outcome, _ = run(config)

    failed = next(r for r in outcome.results if r.target.name == "absent")
    assert failed.status is RepoStatus.FAILED
    assert "not found" in failed.reason
    # Every other repository still produced a result.
    assert len(outcome.results) == 5
    assert any(r.status is RepoStatus.FINDINGS for r in outcome.results)


def test_every_target_repository_has_both_report_forms(estate):
    config, _ = estate
    outcome, layout = run(config)

    for result in outcome.results:
        markdown = layout.report_markdown(HOST, ORG, result.target.name)
        sidecar = layout.report_json(HOST, ORG, result.target.name)
        assert markdown.is_file(), result.target.name
        assert sidecar.is_file(), result.target.name

    assert layout.summary_file.is_file()
    assert layout.summary_json_file.is_file()
    assert layout.summary_html_file.is_file()
    # The coverage check found nothing missing.
    assert not any("no report on disk" in error for error in outcome.run_errors)


def test_the_html_summary_carries_the_same_run_as_the_markdown(estate):
    config, _ = estate
    _, layout = run(config)

    markdown = layout.summary_file.read_text(encoding="utf-8")
    html = layout.summary_html_file.read_text(encoding="utf-8")
    payload = json.loads(layout.summary_json_file.read_text(encoding="utf-8"))

    for key in ("targeted", "scanned", "clean", "with_findings", "skipped", "failed"):
        assert str(payload["totals"][key]) in markdown
        assert str(payload["totals"][key]) in html

    for name, entry in payload["by_match"].items():
        assert name in markdown
        assert name in html
        assert entry["severity"] in html

    # A clean repository is accounted for in the totals rather than linked, so
    # only the ranked and the never-read ones carry a link — in both forms.
    for repository in payload["repositories"]:
        if repository["report"] and repository["status"] != "clean":
            assert repository["report"] in markdown
            assert repository["report"] in html

    # Self-contained: nothing to fetch when it is opened from a file share.
    for external in ("<link", 'src="', "@import"):
        assert external not in html


def test_the_html_summary_bands_its_image_findings(estate):
    config, _ = estate
    _, layout = run(config)

    html = layout.summary_html_file.read_text(encoding="utf-8")
    payload = json.loads(layout.summary_json_file.read_text(encoding="utf-8"))

    assert payload["similarity_threshold"] == 10
    # The band beyond the threshold could never hold a finding, so it is absent.
    assert [band["name"] for band in payload["confidence_bands"]] == [
        "very high",
        "high",
        "medium",
        "low",
    ]
    assert "Likeness confidence" in html
    assert ">very high<" in html


def test_findings_span_text_images_and_inlined_images(estate):
    config, _ = estate
    outcome, layout = run(config)

    payload = json.loads(
        layout.report_json(HOST, ORG, "widgets").read_text(encoding="utf-8")
    )
    kinds = {f["match_type"] for f in payload["findings"]}
    assert kinds == {"text", "image"}

    matched = {f["matched"] for f in payload["findings"]}
    assert "brand-names" in matched
    assert "brand-colours" in matched
    assert "horizontal-lockup" in matched

    # The asset in checked-in build output was found, not excluded.
    assert any(f["path"] == "dist/header.png" for f in payload["findings"])
    # The inlined logo names its containing file.
    assert any(f.get("embedded_in") == "dist/inline.css" for f in payload["findings"])
    # The dependency directory was not searched.
    assert not any(f["path"].startswith("node_modules/") for f in payload["findings"])


def test_permalinks_are_pinned_to_the_scanned_commit(estate):
    config, _ = estate
    outcome, layout = run(config)

    result = next(r for r in outcome.results if r.target.name == "widgets")
    sha = result.provenance.commit_sha
    assert sha
    for finding in result.findings:
        assert finding.permalink.startswith(
            f"https://{HOST}/{ORG}/widgets/blob/{sha}/"
        )


def test_the_summary_accounts_for_every_repository(estate):
    config, _ = estate
    _, layout = run(config)

    payload = json.loads(layout.summary_json_file.read_text(encoding="utf-8"))
    assert payload["counts_reconcile"] is True
    assert {entry["slug"] for entry in payload["repositories"]} == {
        f"{HOST}/{ORG}/{name}"
        for name in ("widgets", "pristine", "dirty", "legacy", "absent")
    }

    markdown = layout.summary_file.read_text(encoding="utf-8")
    assert "## Not scanned" in markdown
    assert "uncommitted modifications" in markdown


# --- Non-destructiveness --------------------------------------------------


def test_a_dirty_external_clone_is_left_exactly_as_it_was(estate):
    config, repos = estate
    dirty = repos["dirty"]
    before_head = git(["rev-parse", "HEAD"], cwd=dirty)
    before_status = git(["status", "--porcelain"], cwd=dirty)

    run(config)

    assert git(["rev-parse", "HEAD"], cwd=dirty) == before_head
    assert git(["status", "--porcelain"], cwd=dirty) == before_status
    assert (dirty / "a.txt").read_text(encoding="utf-8") == "UNCOMMITTED WORK\n"
    assert (dirty / "untracked.md").read_text(encoding="utf-8") == "scratch notes\n"


def test_a_clean_external_clone_is_not_modified_either(estate):
    config, repos = estate
    widgets = repos["widgets"]
    before = git(["rev-parse", "HEAD"], cwd=widgets)

    run(config)

    assert git(["rev-parse", "HEAD"], cwd=widgets) == before
    assert git(["status", "--porcelain"], cwd=widgets) == ""


# --- Resumability ---------------------------------------------------------


def test_re_entering_a_run_does_not_rescan_its_completed_repositories(estate, monkeypatch):
    """Re-entering a run directory restores from its checkpoint, as `--run-id` does."""
    config, _ = estate
    first, layout = run(config)
    assert layout.checkpoint_file.is_file()

    import brandscan.run as run_module

    def refuse(*args, **kwargs):
        raise AssertionError("a completed repository was scanned again")

    monkeypatch.setattr(run_module, "scan_repository", refuse)
    second, _ = run(config, layout=layout)

    assert len(second.results) == len(first.results)
    assert {r.target.name: r.status for r in second.results} == {
        r.target.name: r.status for r in first.results
    }
    # The restored results still carry their findings, so the summary is whole.
    widgets = next(r for r in second.results if r.target.name == "widgets")
    assert widgets.findings


def test_an_interrupted_run_resumes_and_covers_the_full_target_set(estate, monkeypatch):
    """Interrupt mid-run, then resume: the final results cover everything."""
    config, _ = estate
    import brandscan.run as run_module

    real = run_module.scan_repository
    seen: list[str] = []

    def stop_after_two(target, *args, **kwargs):
        if len(seen) >= 2:
            raise KeyboardInterrupt
        seen.append(target.name)
        return real(target, *args, **kwargs)

    monkeypatch.setattr(run_module, "scan_repository", stop_after_two)
    with pytest.raises(KeyboardInterrupt):
        run(config)

    interrupted = latest_layout(config.output_dir)
    partial = json.loads(interrupted.checkpoint_file.read_text(encoding="utf-8"))
    assert len(partial["repositories"]) == 2

    monkeypatch.setattr(run_module, "scan_repository", real)
    outcome, layout = run(config)

    # Re-running the same command continued the interrupted run rather than
    # starting a new one, which is what makes the results cover the whole set.
    assert layout.run_dir == interrupted.run_dir
    assert len(outcome.results) == 5
    assert outcome.totals["targeted"] == 5
    for result in outcome.results:
        assert layout.report_markdown(HOST, ORG, result.target.name).is_file()


def test_refresh_rescans_everything(estate, monkeypatch):
    config, _ = estate
    _, layout = run(config)

    import brandscan.run as run_module

    real = run_module.scan_repository
    scanned: list[str] = []

    def counting(target, *args, **kwargs):
        scanned.append(target.name)
        return real(target, *args, **kwargs)

    monkeypatch.setattr(run_module, "scan_repository", counting)
    # Into the same run directory, so it is the refresh doing the work rather
    # than a fresh directory having no checkpoint to begin with.
    run(config, layout=layout, refresh=True)
    assert len(scanned) == 5


def test_a_missing_report_is_rescanned_rather_than_left_as_a_hole(estate):
    config, _ = estate
    _, layout = run(config)
    layout.report_json(HOST, ORG, "widgets").unlink()
    layout.report_markdown(HOST, ORG, "widgets").unlink()

    outcome, layout = run(config, layout=layout)
    assert layout.report_markdown(HOST, ORG, "widgets").is_file()
    widgets = next(r for r in outcome.results if r.target.name == "widgets")
    assert widgets.findings


# --- Run directories ------------------------------------------------------


def test_two_runs_over_one_output_root_keep_their_own_artifacts(estate):
    """The point of the whole arrangement: the first run survives the second."""
    config, _ = estate
    _, first = run(config)
    before = {
        path: path.read_bytes()
        for path in first.run_dir.rglob("*")
        if path.is_file() and path.name != "run.json"
    }

    _, second = run(config)
    assert second.run_dir != first.run_dir

    for layout in (first, second):
        assert layout.summary_file.is_file()
        for name in ("widgets", "pristine", "dirty", "legacy", "absent"):
            assert layout.report_markdown(HOST, ORG, name).is_file()

    assert {
        path: path.read_bytes()
        for path in first.run_dir.rglob("*")
        if path.is_file() and path.name != "run.json"
    } == before


def test_a_new_run_does_not_inherit_an_earlier_runs_progress(estate, monkeypatch):
    config, _ = estate
    run(config)

    import brandscan.run as run_module

    real = run_module.scan_repository
    scanned: list[str] = []

    def counting(target, *args, **kwargs):
        scanned.append(target.name)
        return real(target, *args, **kwargs)

    monkeypatch.setattr(run_module, "scan_repository", counting)
    outcome, _ = run(config)

    assert len(scanned) == 5
    assert outcome.totals["targeted"] == 5


def test_clones_are_shared_across_runs_and_outside_every_run_directory(estate):
    config, _ = estate
    _, first = run(config)
    _, second = run(config)

    assert first.clones_dir == second.clones_dir == config.output_dir / "clones"
    assert first.run_dir.name not in first.clones_dir.parts
    # Starting a second run neither duplicated the clone tree nor moved it.
    assert not any(
        child.name == "clones" for child in first.run_dir.iterdir()
    )


def test_run_directories_sort_chronologically(estate):
    config, _ = estate
    _, first = run(config)
    _, second = run(config, resume=False)

    names = [run_dir.name for run_dir, _ in discover_runs(config.output_dir)]
    assert names == [second.run_dir.name, first.run_dir.name]


def test_the_run_record_states_what_the_run_was_and_that_it_finished(estate):
    config, _ = estate
    _, layout = run(config)

    record = RunRecord.load(layout.run_record_file)
    assert record is not None
    assert record.run_id == layout.run_dir.name
    assert record.started_at
    assert record.tool_version
    assert record.mode
    assert record.is_finished
    # Identity and lifecycle only: the figures live in the summary, which is
    # rendered from one model precisely so its forms cannot disagree.
    payload = json.loads(layout.run_record_file.read_text(encoding="utf-8"))
    assert not {"findings", "totals", "clean", "scanned"} & set(payload)


def test_an_interrupted_run_is_recorded_as_unfinished(estate, monkeypatch):
    config, _ = estate
    import brandscan.run as run_module

    def stop(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(run_module, "scan_repository", stop)
    with pytest.raises(KeyboardInterrupt):
        run(config)

    layout = latest_layout(config.output_dir)
    record = RunRecord.load(layout.run_record_file)
    assert record is not None
    assert not record.is_finished


def test_a_run_directory_with_an_unreadable_record_is_passed_over(estate):
    config, _ = estate
    _, first = run(config)
    first.run_record_file.write_text("{ truncated", encoding="utf-8")

    _, second = run(config)
    assert second.run_dir != first.run_dir
    # Discovery still lists it; it simply says nothing about its own state.
    assert dict(discover_runs(config.output_dir))[first.run_dir] is None


def test_a_named_run_is_used_outright(estate):
    config, _ = estate
    _, first = run(config)
    assert RunRecord.load(first.run_record_file).is_finished

    named = select_layout(config.output_dir, run_id=first.run_dir.name)
    assert named.run_dir == first.run_dir


def test_an_output_root_holding_older_artifacts_is_left_alone(estate):
    """Artifacts written before run directories existed are not read or moved."""
    config, _ = estate
    legacy_summary = config.output_dir / "executive-summary.md"
    legacy_summary.parent.mkdir(parents=True, exist_ok=True)
    legacy_summary.write_text("an earlier version's summary\n", encoding="utf-8")
    legacy_reports = config.output_dir / "reports"
    legacy_reports.mkdir(parents=True, exist_ok=True)

    _, layout = run(config)

    assert layout.run_dir != config.output_dir
    assert legacy_summary.read_text(encoding="utf-8") == "an earlier version's summary\n"
    assert not any(legacy_reports.iterdir())


# --- The command line -----------------------------------------------------


def test_cli_scan_writes_reports_and_a_log(estate, tmp_path: Path, capsys):
    config, _ = estate
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "brand": {"names": ["Contoso"]},
                "external_repositories": [
                    {
                        "host": HOST,
                        "org": ORG,
                        "name": external.name,
                        "path": str(external.path),
                    }
                    for external in config.external_repositories
                ],
                "output_dir": str(tmp_path / "cli-out"),
            }
        ),
        encoding="utf-8",
    )

    # One repository fails, so a non-zero exit is the intended signal.
    assert main(["scan", "--config", str(config_path), "--mode", "external"]) == 1

    out = capsys.readouterr().out
    assert "Executive summary" in out
    layout = latest_layout(tmp_path / "cli-out")
    assert layout.summary_file.is_file()
    assert layout.report_markdown(HOST, ORG, "widgets").is_file()

    records = [
        json.loads(line)
        for line in layout.log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    started = [r for r in records if r["message"] == "repository scan started"]
    finished = [r for r in records if r["message"] == "repository scan finished"]
    assert len(started) == len(finished) == 5
    assert started[0]["position"] == "1/5"
    # Each finish carries the running counts, so a tailed log tracks the run.
    last = finished[-1]
    assert last["done"] == "5/5"
    assert {"clean", "with_findings", "skipped", "failed"} <= set(last)
    assert any(r["message"] == "brandscan starting" for r in records)


def test_cli_gives_each_invocation_its_own_run_and_can_be_pointed_at_one(
    estate, tmp_path: Path, capsys
):
    config, _ = estate
    output = tmp_path / "runs-out"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "brand": {"names": ["Contoso"]},
                "external_repositories": [
                    {
                        "host": HOST,
                        "org": ORG,
                        "name": "pristine",
                        "path": str(
                            next(
                                e.path
                                for e in config.external_repositories
                                if e.name == "pristine"
                            )
                        ),
                    }
                ],
                "output_dir": str(output),
            }
        ),
        encoding="utf-8",
    )
    command = ["scan", "--config", str(config_path), "--mode", "external"]

    assert main(command) == 0
    first = latest_layout(output).run_dir
    assert f"Run: {first}" in capsys.readouterr().out

    # The first run finished, so the second is a run of its own.
    assert main(command) == 0
    runs = [run_dir for run_dir, _ in discover_runs(output)]
    assert len(runs) == 2
    assert first in runs

    # Naming one re-enters it rather than starting a third.
    assert main(command + ["--run-id", first.name]) == 0
    assert len(discover_runs(output)) == 2
    assert (first / "executive-summary.md").is_file()


def test_cli_reports_a_configuration_error_by_field(tmp_path: Path, capsys):
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(
        yaml.safe_dump({"targets": [{"host": "github.com"}], "brand": {"names": ["x"]}}),
        encoding="utf-8",
    )
    assert main(["scan", "--config", str(config_path)]) == 2
    assert "targets[0].org" in capsys.readouterr().err


def test_cli_validate_config_does_not_acquire_anything(tmp_path: Path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "targets": [{"host": "github.com", "org": "contoso"}],
                "brand": {"names": ["Contoso"]},
            }
        ),
        encoding="utf-8",
    )
    assert main(["validate-config", "--config", str(config_path)]) == 0
    out = capsys.readouterr().out
    assert "Configuration is valid" in out
    assert "similarity threshold: 10 (default)" in out


def test_cli_external_root_works_without_any_configured_target(estate, tmp_path: Path):
    """The standalone form the README documents.

    Validation used to run before the flag was applied, so a config naming no
    targets was rejected before `--external-root` could supply any.
    """
    config, repos = estate
    root = repos["widgets"].parent

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {"brand": {"names": ["Contoso"]}, "output_dir": str(tmp_path / "root-out")}
        ),
        encoding="utf-8",
    )

    exit_code = main(["scan", "--config", str(config_path), "--external-root", str(root)])
    assert exit_code in (0, 1)

    layout = latest_layout(tmp_path / "root-out")
    assert layout.summary_file.is_file()
    # Hosts and organisations were derived from each clone's own remote.
    assert layout.report_markdown(HOST, ORG, "widgets").is_file()
    assert layout.report_markdown(HOST, ORG, "pristine").is_file()


def test_cli_repo_flag_narrows_a_configured_target(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "targets": [{"host": HOST, "org": ORG}],
                "brand": {"names": ["Contoso"]},
                "output_dir": str(tmp_path / "narrow-out"),
            }
        ),
        encoding="utf-8",
    )

    from brandscan import run as run_module

    captured = {}

    def capture(config, layout, **kwargs):
        captured["targets"] = list(config.targets)
        raise SystemExit(0)

    monkeypatch.setattr(run_module, "execute_run", capture)
    monkeypatch.setattr("brandscan.cli.execute_run", capture)

    with pytest.raises(SystemExit):
        main(
            [
                "scan",
                "--config",
                str(config_path),
                "--repo",
                f"{ORG}/legacy-webforms",
                "--repo",
                f"{ORG}/checkout-ui",
            ]
        )

    assert len(captured["targets"]) == 1
    assert captured["targets"][0].repos == ("legacy-webforms", "checkout-ui")


def test_cli_repo_flag_rejects_an_unknown_organisation(tmp_path: Path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {"targets": [{"host": HOST, "org": ORG}], "brand": {"names": ["Contoso"]}}
        ),
        encoding="utf-8",
    )
    assert main(["scan", "--config", str(config_path), "--repo", "fabrikam/widgets"]) == 2
    err = capsys.readouterr().err
    assert "no configured target for organisation" in err
    assert "github.com/contoso" in err


def test_cli_repo_flag_rejects_a_malformed_selector(tmp_path: Path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {"targets": [{"host": HOST, "org": ORG}], "brand": {"names": ["Contoso"]}}
        ),
        encoding="utf-8",
    )
    assert main(["scan", "--config", str(config_path), "--repo", "justaname"]) == 2
    assert "ORG/NAME or HOST/ORG/NAME" in capsys.readouterr().err


def test_an_unquoted_company_number_is_actually_found_by_a_scan(tmp_path: Path):
    """The requirement is about what a scan finds, not what validation accepts.

    `07654321` is all octal digits behind a leading zero, so YAML 1.1 parses it
    as 2054353. If the loader searched for the parsed value, this repository
    would be reported clean while plainly carrying the number.
    """
    work = tmp_path / "work"
    repo = make_git_repo(
        work / "accounts",
        f"https://{HOST}/{ORG}/accounts.git",
        {"footer.html": "<p>Contoso Limited, registered in England, "
                        "company number 07654321.</p>\n"},
    )

    config_path = tmp_path / "config.yaml"
    # Written as text, not dumped: a dump would quote the numeral and so would
    # never exercise the path this test exists for.
    config_path.write_text(
        f"""
brand:
  legal:
    - 07654321
external_repositories:
  - host: {HOST}
    org: {ORG}
    name: accounts
    path: {repo.as_posix()}
output_dir: {(tmp_path / "num-out").as_posix()}
""",
        encoding="utf-8",
    )

    assert main(["scan", "--config", str(config_path), "--mode", "external"]) == 0

    layout = latest_layout(tmp_path / "num-out")
    payload = json.loads(
        layout.report_json(HOST, ORG, "accounts").read_text(encoding="utf-8")
    )
    assert payload["findings"], "the company number was not found"
    excerpts = " ".join(f.get("excerpt", "") for f in payload["findings"])
    assert "07654321" in excerpts
    assert "2054353" not in excerpts


def test_cli_mode_external_ignores_host_targets(estate, tmp_path: Path):
    config, _ = estate
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "targets": [{"host": "unreachable.invalid", "org": "nobody"}],
                "brand": {"names": ["Contoso"]},
                "external_repositories": [
                    {
                        "host": HOST,
                        "org": ORG,
                        "name": "pristine",
                        "path": str(
                            next(
                                e.path
                                for e in config.external_repositories
                                if e.name == "pristine"
                            )
                        ),
                    }
                ],
                "output_dir": str(tmp_path / "ext-out"),
            }
        ),
        encoding="utf-8",
    )
    # No preflight runs, because --mode external drops the host targets.
    assert main(["scan", "--config", str(config_path), "--mode", "external"]) == 0
