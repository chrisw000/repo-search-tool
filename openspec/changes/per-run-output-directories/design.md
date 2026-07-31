## Context

See proposal.md — Why.

What shapes the approach is that `OutputLayout` is currently a single-root
dataclass and every artifact path hangs off `root`. Four consumers depend on
that root: `cli.py` builds the layout and configures logging against
`layout.log_file` *before* the run starts; `run.py` reads and writes the
checkpoint and the reports; `_rehydrate` recovers a completed repository from
its own report sidecar, so resumption is coupled to where reports live; and
`summary_relative_link` computes the summary's links as paths relative to the
root.

Two of the repository's load-bearing invariants bear directly on this change.
Invariant 4 (two safety postures) hangs off the clone tree specifically —
`clones/` may be hard-reset, external directories never touched — so wherever
clones end up, they must stay the one tree the reset guard knows about.
Invariant 10 (one model behind all three summary renderings) constrains what
the new run record is allowed to contain.

## Goals / Non-Goals

**Goals:**

- One run's artifacts are addressable, complete and self-describing without
  reference to any other run.
- The existing operator promise — "re-run the same command to resume" — keeps
  working literally, with no new flag required.
- The change is confined to path derivation and run selection. No scanning,
  matching, reporting or aggregation logic moves.

**Non-Goals:**

- Comparing runs, or any tooling over the accumulated run directories.
- Retention, pruning, or an upper bound on run directories.
- Migrating artifacts written by earlier versions into a run directory.

## Decisions

### D1 — Split the layout into an output root and a run directory

`OutputLayout` keeps `root` as the *output root* and gains `run_dir`. Only
`clones_dir` and run discovery hang off `root`; `reports_dir`,
`checkpoint_file`, `log_file`, the three summary files and the new run record
hang off `run_dir`. `summary_relative_link` becomes relative to `run_dir`,
which leaves the summary's links textually identical to what they are today —
the summary and the reports move down together.

*Alternative considered:* a second dataclass for the run, leaving `OutputLayout`
alone. Rejected because every consumer needs both roots, so it would only push
the pairing into four call sites instead of holding it in the one type that
exists to answer "where does this go".

`bootstrap()` creates the run directory as well as the clone tree, keeping the
single place that establishes the skeleton.

### D2 — Name run directories from the start instant in UTC

`YYYY-MM-DD-HHMMSS-run`, formatted from the run's start instant in UTC. Sorting
by name is sorting by time, which is the property the operator actually uses
when comparing runs, and it needs no index or metadata read.

UTC rather than local time, for two reasons. Every other instant the tool
records — `Provenance.scanned_at`, the JSONL log, the run record's own
`started_at` — is UTC ISO, and a directory name in local time would be the one
timestamp in the tree that could not be lined up against the others. More
sharply, local time is not monotonic: at the autumn DST fold an hour of
timestamps repeats, so a name derived from local time can collide with a name
from an hour earlier. UTC has no fold.

*Trade-off:* during British Summer Time the directory name reads an hour behind
the operator's clock. Accepted, because the run record inside carries the same
instant and the ordering — the thing being relied on — is unaffected.

*Collision handling:* two runs starting in the same second, or a name already
taken, get `-2`, `-3`, … appended. This is cheap insurance rather than an
expected case; the point is that a run never writes into a directory it did not
create.

### D3 — A run record, and the fact it deliberately does not carry totals

`run.json` in the run directory holds: schema version, run id, `started_at`,
`finished_at` (null while running), tool version, configuration source path, and
acquisition mode.

`finished_at` is what makes run selection possible (D4) — without it, "is the
latest run still going?" cannot be answered, and every re-invocation would have
to either always resume or always start afresh.

It carries **no finding counts and no totals**. Invariant 10 exists because
three renderings of the same rollup must not be able to disagree; a fourth
artifact restating the same figures, computed at a different point in the run,
would be exactly the drift that invariant forbids. Cross-run comparison reads
`executive-summary.json`, which is already the machine-readable rollup. The run
record answers *which run is this*, not *what did it find*.

Writing it is not atomic-critical the way the checkpoint is — losing it costs a
resume, not a scan — but it uses the same write-temp-then-replace as
`Checkpoint.save`, since the code is already there and a half-written record
would make the run undiscoverable.

### D4 — Run selection: continue the latest unfinished run, else start a new one

Selection happens in `cli.py` before logging is configured, because the log now
lives inside the chosen run directory. The rule:

1. `--run-id NAME` given → use `<output>/NAME`, creating it if absent. Explicit
   naming wins over everything, including whether that run finished.
2. `--no-resume` or `--refresh` → new run directory. Both mean "scan everything
   again", so their results are a new run's, not an amendment to an old one.
3. Otherwise → the newest run directory whose record has no `finished_at` is
   continued; if none, a new run directory is created.

This preserves today's behaviour exactly where it matters. An interrupted run is
resumed by re-running the same command, so the message printed on Ctrl-C stays
true. A completed run is no longer silently re-entered to do nothing — the
re-invocation is taken at face value as a new run, which is the behaviour the
proposal is for.

*Alternative considered:* always create a new run directory, and require
`--run-id` to resume. Rejected because it breaks the resume promise for the case
that motivated checkpointing in the first place — an unattended ~400-repository
run that dies overnight — and makes the recovery path depend on the operator
having noted a directory name.

*Alternative considered:* keep the latest run directory as the default target
whether or not it finished, matching today's semantics exactly. Rejected because
it defeats the change: the common case, re-running after a completed scan, would
still overwrite.

*Consequence:* a plain re-run after a completed run now re-acquires and re-scans
the whole target set, where today it does nothing. That cost is real but it is
the cost of the thing being asked for, and it falls on scanning rather than
cloning, since clones are shared (D5). `--run-id <previous>` remains the way to
add to an earlier run instead.

The newest unfinished run is found by listing directories matching the naming
pattern, taking them in reverse name order, and reading the first record that
parses. A directory that does not parse is skipped rather than treated as a
failure — an unreadable record from a hard kill must not block a new run.

### D5 — Clones stay at the output root, shared

`clones/` does not move. Three reasons, in order of weight.

Disk: ~400 shallow clones is the bulk of the output tree, and per-run clones
would multiply it by the number of runs kept — which directly punishes the
practice this change is meant to encourage.

Safety: invariant 4 draws the hard-reset boundary around `clones/`, guarded by
an origin-URL check. Keeping exactly one such tree keeps that boundary a single
statement instead of one per run.

Semantics: a clone is a working copy, not evidence. What a run saw in it is
already captured in that run's reports, pinned by `commit_sha` in the
provenance block — which is what makes two runs comparable in the first place,
since a difference between them can be attributed to a commit rather than
guessed at.

### D6 — Earlier artifacts are left alone, not migrated

An output root written by an earlier version holds `reports/`,
`executive-summary.*`, `checkpoint.json` and `run.log.jsonl` at its top level.
The new code neither reads nor moves them: they carry no run record, so run
discovery does not see them, and the first run under the new layout creates a
fresh run directory.

*Alternative considered:* migrating them into a synthesised run directory on
first sight. Rejected as a one-shot piece of code, executed once per operator,
whose failure modes land on the only copy of an earlier run's output. Leaving
them in place costs one full re-scan and cannot lose anything; the operator can
move or delete them by hand once they no longer want them.

## Risks / Trade-offs

- **A plain re-run now costs a full re-scan where it previously cost nothing.**
  → It is the intended behaviour, and it is stated in the proposal as breaking.
  The mitigations are `--run-id <previous>` to continue an earlier run, and the
  fact that clones are shared so acquisition is a fetch rather than a clone.

- **Run directories accumulate without bound.** → Out of scope by decision; a
  run's tree is small next to the clones, and no automatic deletion of an
  operator's evidence is going in without them asking for it.

- **A hard-killed run leaves `finished_at` null forever, so the next invocation
  resumes it.** → That is the correct reading of an interrupted run. `--no-resume`
  starts a new one, and `--refresh` re-scans; both are already flags the
  operator has.

- **Tooling or scripts pointing at `<output>/executive-summary.md` break.** →
  Accepted and called out as breaking. The CLI prints the run directory and the
  summary path on every run, and the run directory sorts last by name, so the
  latest summary stays trivially locatable.

- **Two concurrent runs against one output root now write separate report trees
  but still share the clone tree**, so they can fight over a working copy. →
  Pre-existing: this is equally true today, and this change does not make it
  worse. Not addressed here.
