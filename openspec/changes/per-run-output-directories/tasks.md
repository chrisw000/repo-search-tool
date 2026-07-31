## 1. Failing tests first

- [ ] 1.1 Add tests for run-directory naming: a start instant formats as `YYYY-MM-DD-HHMMSS-run` in UTC, and names for successive instants sort chronologically
- [ ] 1.2 Add a test that a run whose derived name is already taken gets a distinct directory rather than reusing it
- [ ] 1.3 Add tests that `OutputLayout` puts reports, the three summary files, the checkpoint, the log and the run record inside the run directory, and the clone tree at the output root
- [ ] 1.4 Add a test that `summary_relative_link` is unchanged in form and resolves within the run directory
- [ ] 1.5 Add tests for the run record: it carries run id, `started_at`, tool version, config source and mode; `finished_at` is null while running and set on completion
- [ ] 1.6 Add tests for run selection — an unfinished latest run is continued, a finished latest run causes a new run, no runs at all causes a new run, `--run-id` wins outright, and `--no-resume` / `--refresh` each force a new run
- [ ] 1.7 Add a test that a run directory whose record is missing or unparseable is skipped by discovery rather than ending the run
- [ ] 1.8 Add an end-to-end test that two runs over one output root each produce a complete report tree and summary, that the first run's artifacts are byte-identical before and after the second, and that both runs share the same clones
- [ ] 1.9 Add a test that an output root holding pre-run-directory artifacts is neither read nor modified, and that a new run directory is created

## 2. Run naming and layout

- [ ] 2.1 Add run-directory naming to `paths.py`: format a start instant into a run id, and resolve a collision by suffixing
- [ ] 2.2 Split `OutputLayout` into output root (`root`) and `run_dir`, re-pointing `reports_dir`, `checkpoint_file`, `log_file` and the three summary files at `run_dir` and leaving `clones_dir` on `root`
- [ ] 2.3 Add `run_record_file` to the layout and make `summary_relative_link` relative to `run_dir`
- [ ] 2.4 Extend `bootstrap()` to create the run directory alongside the clone tree
- [ ] 2.5 Verify 1.1–1.4 pass

## 3. The run record

- [ ] 3.1 Add the run record type: schema version, run id, `started_at`, `finished_at`, tool version, config source, mode — and no finding counts or totals, per design D3
- [ ] 3.2 Write it atomically on the same write-temp-then-replace pattern as `Checkpoint.save`
- [ ] 3.3 Load a record tolerantly: a missing, truncated or wrong-version file reads as absent rather than raising
- [ ] 3.4 Verify 1.5 and 1.7 pass

## 4. Run selection

- [ ] 4.1 Add discovery of run directories under an output root: match the naming pattern, order by name descending, and read records skipping any that do not parse
- [ ] 4.2 Add the selection rule from design D4 — explicit `--run-id`, then `--no-resume` / `--refresh` forcing a new run, then continue the newest unfinished run, else new
- [ ] 4.3 Add the `--run-id NAME` argument to the `scan` parser, with help text saying it selects an existing run or names a new one
- [ ] 4.4 Apply selection in `_run_scan` before `configure_logging`, so the log lands in the chosen run directory
- [ ] 4.5 Verify 1.6 passes

## 5. Wiring the run

- [ ] 5.1 Write the run record when the run starts, before the first repository is acquired
- [ ] 5.2 Complete the record with `finished_at` when `execute_run` returns, including when the run finished with per-repository failures or run-level errors
- [ ] 5.3 Leave the record incomplete on interrupt, so the run is resumable, and confirm the Ctrl-C message remains accurate
- [ ] 5.4 Report the run directory to the operator alongside the summary path, and log it in the run-started log line
- [ ] 5.5 Verify 1.8 and 1.9 pass

## 6. Existing suite and documentation

- [ ] 6.1 Move the path assertions in `tests/test_end_to_end.py` and `tests/test_reporting.py` down into the run directory, and confirm the resume tests still assert resumption within one run
- [ ] 6.2 Run the full suite and confirm it passes
- [ ] 6.3 Update `CLAUDE.md`: the output layout, the new invariant that clones are shared while everything else is per-run, the run-record-carries-no-totals rule under invariant 10, and the test count
- [ ] 6.4 Update `README` / config sample wording where it describes `output_dir` and where reports appear, if it does
- [ ] 6.5 Run `openspec validate per-run-output-directories --strict`
