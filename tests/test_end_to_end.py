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
from brandscan.paths import OutputLayout
from brandscan.results import RepoStatus
from brandscan.run import execute_run
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


def run(config, resume=True, refresh=False):
    layout = OutputLayout(root=config.output_dir)
    return execute_run(config, layout, resume=resume, refresh=refresh), layout


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
    # The coverage check found nothing missing.
    assert not any("no report on disk" in error for error in outcome.run_errors)


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


def test_a_resumed_run_does_not_rescan_completed_repositories(estate, monkeypatch):
    config, _ = estate
    first, layout = run(config)
    assert layout.checkpoint_file.is_file()

    import brandscan.run as run_module

    def refuse(*args, **kwargs):
        raise AssertionError("a completed repository was scanned again")

    monkeypatch.setattr(run_module, "scan_repository", refuse)
    second, _ = run(config)

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

    layout = OutputLayout(root=config.output_dir)
    partial = json.loads(layout.checkpoint_file.read_text(encoding="utf-8"))
    assert len(partial["repositories"]) == 2

    monkeypatch.setattr(run_module, "scan_repository", real)
    outcome, layout = run(config)

    assert len(outcome.results) == 5
    assert outcome.totals["targeted"] == 5
    for result in outcome.results:
        assert layout.report_markdown(HOST, ORG, result.target.name).is_file()


def test_refresh_rescans_everything(estate, monkeypatch):
    config, _ = estate
    run(config)

    import brandscan.run as run_module

    real = run_module.scan_repository
    scanned: list[str] = []

    def counting(target, *args, **kwargs):
        scanned.append(target.name)
        return real(target, *args, **kwargs)

    monkeypatch.setattr(run_module, "scan_repository", counting)
    run(config, refresh=True)
    assert len(scanned) == 5


def test_a_missing_report_is_rescanned_rather_than_left_as_a_hole(estate):
    config, _ = estate
    _, layout = run(config)
    layout.report_json(HOST, ORG, "widgets").unlink()
    layout.report_markdown(HOST, ORG, "widgets").unlink()

    outcome, layout = run(config)
    assert layout.report_markdown(HOST, ORG, "widgets").is_file()
    widgets = next(r for r in outcome.results if r.target.name == "widgets")
    assert widgets.findings


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
    layout = OutputLayout(root=tmp_path / "cli-out")
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
