"""Where a run's artifacts go, and which run an invocation joins.

The whole point of the arrangement is that one run's output cannot be destroyed
by the next, so these tests are about directory identity rather than about
anything the scan finds.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from brandscan.paths import (
    OutputLayout,
    create_run_dir,
    discover_runs,
    run_id_for,
    select_layout,
)
from brandscan.run_record import RunRecord

HOST = "github.com"
ORG = "contoso"

STARTED = datetime(2026, 7, 31, 14, 25, 30, tzinfo=timezone.utc)


def record(run_id: str, finished: bool) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        started_at="2026-07-31T14:25:30+00:00",
        tool_version="0.0.0",
        mode="both",
        finished_at="2026-07-31T14:40:00+00:00" if finished else None,
    )


def finished_run(root: Path, at: datetime) -> Path:
    run_dir = create_run_dir(root, at)
    record(run_dir.name, finished=True).write(run_dir / "run.json")
    return run_dir


def unfinished_run(root: Path, at: datetime) -> Path:
    run_dir = create_run_dir(root, at)
    record(run_dir.name, finished=False).write(run_dir / "run.json")
    return run_dir


# --- Naming ---------------------------------------------------------------


def test_a_run_is_named_for_its_start_instant_in_utc():
    assert run_id_for(STARTED) == "2026-07-31-142530-run"


def test_a_local_time_is_converted_rather_than_taken_at_face_value():
    """British Summer Time is an hour ahead; the name is the UTC instant."""
    bst = timezone(timedelta(hours=1))
    assert run_id_for(datetime(2026, 7, 31, 15, 25, 30, tzinfo=bst)) == (
        "2026-07-31-142530-run"
    )


def test_names_for_successive_instants_sort_chronologically():
    instants = [STARTED + timedelta(seconds=n) for n in (0, 30, 3600, 90000)]
    names = [run_id_for(instant) for instant in instants]
    assert names == sorted(names)


def test_two_runs_in_one_second_get_distinct_directories(tmp_path: Path):
    first = create_run_dir(tmp_path, STARTED)
    second = create_run_dir(tmp_path, STARTED)
    assert first != second
    assert first.is_dir() and second.is_dir()
    assert first.name == "2026-07-31-142530-run"
    assert second.name == "2026-07-31-142530-run-2"


# --- Layout ---------------------------------------------------------------


def layout_for(tmp_path: Path) -> OutputLayout:
    return OutputLayout(root=tmp_path, run_dir=tmp_path / "2026-07-31-142530-run")


def test_a_runs_own_artifacts_live_in_its_run_directory(tmp_path: Path):
    layout = layout_for(tmp_path)
    for path in (
        layout.reports_dir,
        layout.checkpoint_file,
        layout.log_file,
        layout.run_record_file,
        layout.summary_file,
        layout.summary_json_file,
        layout.summary_html_file,
        layout.report_markdown(HOST, ORG, "widgets"),
    ):
        assert layout.run_dir in path.parents


def test_the_clone_tree_is_shared_at_the_output_root(tmp_path: Path):
    layout = layout_for(tmp_path)
    assert layout.clones_dir == tmp_path / "clones"
    assert layout.run_dir not in layout.repo_dir(HOST, ORG, "widgets").parents


def test_bootstrap_creates_the_run_directory_and_the_clone_tree(tmp_path: Path):
    layout = layout_for(tmp_path)
    layout.bootstrap()
    assert layout.run_dir.is_dir()
    assert layout.reports_dir.is_dir()
    assert layout.clones_dir.is_dir()


def test_a_summary_links_to_reports_within_its_own_run(tmp_path: Path):
    layout = layout_for(tmp_path)
    link = layout.summary_relative_link(HOST, ORG, "widgets")
    assert link == "reports/github.com/contoso/widgets/report.md"
    assert (layout.summary_file.parent / link) == layout.report_markdown(
        HOST, ORG, "widgets"
    )


# --- The run record -------------------------------------------------------


def test_a_record_round_trips(tmp_path: Path):
    written = RunRecord(
        run_id="2026-07-31-142530-run",
        started_at="2026-07-31T14:25:30+00:00",
        tool_version="1.2.3",
        mode="external",
        config_source="C:/scan.yaml",
    )
    written.write(tmp_path / "run.json")
    read = RunRecord.load(tmp_path / "run.json")

    assert read == written
    assert not read.is_finished


def test_a_finished_record_says_when_it_finished(tmp_path: Path):
    written = record("2026-07-31-142530-run", finished=True)
    written.write(tmp_path / "run.json")
    read = RunRecord.load(tmp_path / "run.json")
    assert read.is_finished
    assert read.finished_at == "2026-07-31T14:40:00+00:00"


def test_a_missing_record_reads_as_absent(tmp_path: Path):
    assert RunRecord.load(tmp_path / "nothing.json") is None


def test_a_truncated_record_reads_as_absent_rather_than_raising(tmp_path: Path):
    (tmp_path / "run.json").write_text('{"version": 1, "run_', encoding="utf-8")
    assert RunRecord.load(tmp_path / "run.json") is None


def test_a_record_of_an_unrecognised_version_reads_as_absent(tmp_path: Path):
    (tmp_path / "run.json").write_text(
        '{"version": 99, "run_id": "x", "started_at": "y"}', encoding="utf-8"
    )
    assert RunRecord.load(tmp_path / "run.json") is None


# --- Discovery and selection ----------------------------------------------


def test_discovery_lists_runs_most_recent_first(tmp_path: Path):
    older = finished_run(tmp_path, STARTED)
    newer = finished_run(tmp_path, STARTED + timedelta(hours=2))
    assert [run_dir for run_dir, _ in discover_runs(tmp_path)] == [newer, older]


def test_discovery_ignores_directories_that_are_not_runs(tmp_path: Path):
    (tmp_path / "clones").mkdir()
    (tmp_path / "reports").mkdir()
    run_dir = finished_run(tmp_path, STARTED)
    assert [path for path, _ in discover_runs(tmp_path)] == [run_dir]


def test_discovery_lists_a_run_whose_record_did_not_survive(tmp_path: Path):
    run_dir = create_run_dir(tmp_path, STARTED)
    (run_dir / "run.json").write_text("{ truncated", encoding="utf-8")
    assert discover_runs(tmp_path) == [(run_dir, None)]


def test_discovery_of_an_output_root_that_does_not_exist_is_empty(tmp_path: Path):
    assert discover_runs(tmp_path / "never-run") == []


def test_an_unfinished_run_is_continued(tmp_path: Path):
    run_dir = unfinished_run(tmp_path, STARTED)
    assert select_layout(tmp_path).run_dir == run_dir


def test_a_finished_run_is_left_alone_in_favour_of_a_new_one(tmp_path: Path):
    run_dir = finished_run(tmp_path, STARTED)
    selected = select_layout(tmp_path, now=STARTED + timedelta(hours=1))
    assert selected.run_dir != run_dir
    assert selected.run_dir.name == "2026-07-31-152530-run"


def test_a_first_run_creates_a_run_directory(tmp_path: Path):
    selected = select_layout(tmp_path, now=STARTED)
    assert selected.run_dir == tmp_path / "2026-07-31-142530-run"
    assert selected.run_dir.is_dir()


def test_a_named_run_wins_whether_or_not_it_finished(tmp_path: Path):
    finished = finished_run(tmp_path, STARTED)
    unfinished_run(tmp_path, STARTED + timedelta(hours=1))
    assert select_layout(tmp_path, run_id=finished.name).run_dir == finished


def test_a_named_run_that_does_not_exist_yet_is_created_on_bootstrap(tmp_path: Path):
    selected = select_layout(tmp_path, run_id="a-trial-run")
    assert selected.run_dir == tmp_path / "a-trial-run"
    selected.bootstrap()
    assert selected.run_dir.is_dir()


def test_forcing_a_new_run_leaves_an_unfinished_one_alone(tmp_path: Path):
    """`--no-resume` and `--refresh` both mean a new run's worth of results."""
    run_dir = unfinished_run(tmp_path, STARTED)
    selected = select_layout(tmp_path, force_new=True, now=STARTED + timedelta(hours=1))
    assert selected.run_dir != run_dir


def test_a_run_whose_record_did_not_survive_is_passed_over(tmp_path: Path):
    run_dir = create_run_dir(tmp_path, STARTED)
    (run_dir / "run.json").write_text("{ truncated", encoding="utf-8")
    selected = select_layout(tmp_path, now=STARTED + timedelta(hours=1))
    assert selected.run_dir != run_dir


def test_only_the_most_recent_recorded_run_is_a_candidate(tmp_path: Path):
    """A finished newer run supersedes an older unfinished one."""
    unfinished_run(tmp_path, STARTED)
    finished_run(tmp_path, STARTED + timedelta(hours=1))
    selected = select_layout(tmp_path, now=STARTED + timedelta(hours=2))
    assert selected.run_dir.name == "2026-07-31-162530-run"
