## Why

Every run writes its reports and its executive summary to the same fixed paths
under the output root, so a second run silently overwrites the first. The
rebrand is not a one-shot exercise — repositories get fixed and re-scanned, the
reference set grows, the threshold gets tuned — and the question the operator
most wants answered is "what changed since last time". Today the evidence for
that question is destroyed by the act of asking it.

A run is also not currently a thing the output tree names. Its log, its
checkpoint, its reports and its summary are four artifacts scattered at the
root with no marker saying which run produced them or whether that run ever
finished.

## What Changes

- Each run writes its artifacts into its own **run directory** under the output
  root, named `YYYY-MM-DD-HHMMSS-run` from the run's start instant in UTC. The
  run's reports tree, executive summary (all three renderings), checkpoint and
  JSON log all live inside it. Successive runs therefore sit side by side and
  sort chronologically.
- **Clones stay where they are**, shared at the output root, outside every run
  directory. They are the expensive part of a run and they carry no per-run
  information; copying them per run would multiply the disk cost of a
  ~400-repository scan for nothing.
- Each run directory carries a small **run record** (`run.json`) naming the run,
  when it started, when it finished, the tool version, the configuration it read
  and the acquisition mode — so a run directory says what it is without being
  reverse-engineered from its contents, and so an interrupted run is
  distinguishable from a completed one.
- **Re-invocation picks its run directory from that record.** An interrupted run
  is resumed in place, so the existing promise that re-running the same command
  resumes it holds unchanged. When the latest run finished, a re-invocation
  starts a new run directory rather than rewriting the finished one — which is
  what makes two runs comparable.
- A new `--run-id NAME` selects a run directory by name outright, for adding to
  or re-doing a specific earlier run.
- `--no-resume` and `--refresh` start a new run directory, since both mean "scan
  everything again" and their results belong to a new run.
- **BREAKING** (output layout only, no scanned repository is affected): report
  and summary paths move from `<output>/reports/...` and
  `<output>/executive-summary.*` down one level into the run directory. Artifacts
  written by earlier versions are left in place, untouched and unread; the first
  run under the new layout starts a fresh run directory and does not inherit the
  old root checkpoint, so it re-scans. Clones are unaffected, so that cost is
  scanning, not re-cloning.

Not in scope: comparing or diffing two runs. This change makes comparison
possible by keeping the evidence; it does not add a comparison feature. Nor is
there any retention or pruning policy — run directories accumulate until the
operator removes them.

## Capabilities

### New Capabilities

- `run-output-layout`: where a run's artifacts are written, how a run directory
  is named and identified, what distinguishes an unfinished run from a finished
  one, and how a re-invocation chooses between continuing a run and starting a
  new one. Also fixes what is deliberately *not* per-run — the repository clones.

### Modified Capabilities

- `repository-acquisition`: the resumable-runs requirement gains the scope it
  has always implicitly had — a checkpoint belongs to one run, resumption
  continues that run's directory, and a run started fresh does not resume
  another run's checkpoint.

## Impact

- `src/brandscan/paths.py` — `OutputLayout` splits its single root into the
  output root (clones) and a run directory (everything else); run-directory
  naming, collision handling and discovery of the latest run live here.
- New `src/brandscan/run_record.py` (or equivalent) — the run record's shape,
  writing it at start and completing it at the end.
- `src/brandscan/cli.py` — the `--run-id` flag, run-directory selection before
  logging is configured (the log now lives inside the run directory), and
  reporting the chosen run directory to the operator.
- `src/brandscan/run.py` — marks the run record complete on the way out.
- `tests/test_end_to_end.py`, `tests/test_reporting.py` — every path assertion
  moves down one level; new coverage for selection, resumption and isolation
  between two runs over the same output root.
- No configuration change: `output_dir` keeps its meaning as the output root.
- No new dependency.
