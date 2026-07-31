# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

`brandscan` — a CLI that finds traces of an old brand across ~400 repositories
spread over two GitHub hosts (one Enterprise Server, one github.com, each behind
its own SSO), by image content and text pattern. It emits one Markdown report
per repository plus one executive summary.

**It finds and reports only. It must never edit a scanned repository.** The
per-repo report is the hand-off: it is fed to an AI coding agent later to
perform the fixes, which is why its structure is a contract rather than a
presentation choice.

This repo is also the mechanics run for evaluating OpenSpec's
propose → review → apply loop, so the spec is the source of truth for behaviour,
not the code.

## Environment

```powershell
# The venv already exists. Rebuild it only if it is missing:
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# Tests — full suite is ~55s, currently 295 passing.
.\.venv\Scripts\python.exe -m pytest -q

# A single file while iterating.
.\.venv\Scripts\python.exe -m pytest tests/test_images.py -q
```

Always invoke the venv interpreter by path. There is no activated shell between
tool calls, so a bare `python` or `pytest` hits the system install and fails on
missing dependencies.

The `openspec` CLI is installed via pnpm but is **not on PATH**. Prefix every
call:

```powershell
$env:PATH = "C:\Users\chris\AppData\Local\pnpm;$env:PATH"; openspec list --json
```

## Layout

```
src/brandscan/
  cli.py            argument parsing, mode selection, exit codes
  run.py            the orchestrator: acquire -> scan -> report -> roll up
  results.py        RepoResult / RepoStatus / Provenance
  findings.py       Finding and ScanIssue — the unit both searches produce
  paths.py          output layout: shared root vs per-run directory, run
                    naming, discovery and selection; namespaced host/org/repo
  run_record.py     what a run directory says about itself, incl. whether the
                    run finished — the basis for resuming one
  atomic.py         write-temp-then-replace, shared by checkpoint and record
  logging_setup.py  JSONL run log and RunProgress counters
  config/           loader (field-named validation), model, seeded groups,
                    references, scalars (source-text-preserving YAML)
  acquisition/      preflight, enumeration, clone/refresh, checkpoint, gh+git wrappers
  scan/             walker, text search, base64 extraction, image search driver
  images/           trim, hashing, SVG rasterisation, matching strategy seam
  report/           per-repo markdown + JSON sidecar, permalinks; summary_model
                    computes the rollup, summary/html render it (plus the sidecar)
tests/              mirrors the above; conftest.py builds synthetic logos and git repos
openspec/specs/     the current behaviour contract — six capabilities, source of truth
openspec/changes/   in-flight changes; archive/ holds the ones already folded into specs/
```

## Load-bearing invariants

Do not "simplify" these away. Each encodes a decision (the `Dn` references
below) recorded in
`openspec/changes/archive/2026-07-31-brand-asset-discovery-scanner/design.md`,
except invariant 9, whose decisions live in
`openspec/changes/archive/2026-07-31-accept-numeric-config-scalars/design.md`,
invariants 10–12, whose decisions live in
`openspec/changes/archive/2026-07-31-enrich-executive-summary/design.md`, and
invariants 13–14, whose decisions live in
`openspec/changes/per-run-output-directories/design.md` (not yet archived).

1. **Trim before any colour-mode conversion** (`images/trim.py`, D2).
   Converting an opaque image to RGBA first gives it a full-frame alpha channel;
   the trim then finds content everywhere and silently becomes a no-op, and
   matching quietly degrades with no error anywhere. `images/hashing.py`
   `signature_for()` is the only entry point, and it fixes the order.

2. **Hash on luminance** (`images/hashing.py`, D3). Colour-blindness is the
   point: the reference set carries one image per *layout*, and recoloured
   copies nobody catalogued are caught for free.

3. **Never assume `main`** (D5). Default branches come from the API's
   `default_branch`. Legacy repositories default to `master`/`develop`/`trunk`
   and are the ones most likely to hold stale branding — guessing would produce
   an empty scan rather than an error.

4. **Two safety postures** (`acquisition/clone.py`, D6). Managed clones under
   `clones/` are hard-reset freely, guarded by an origin-URL check. User-supplied
   external directories are **never** written to; a dirty one is skipped with a
   recorded reason, never reset.

5. **Build output is not excluded** (`config/defaults.py`, D9). Deployed brand
   assets frequently exist only in `dist`/`build`/`wwwroot`. Duplicate findings
   are cheap; a confident miss is not.

6. **Clean is not the same as skipped or failed** (`results.py`, D10). A
   repository that was never read must never be reported as having no findings.

7. **Per-repository failure isolation** (`run.py`). Nothing a single repository
   does may end a run over hundreds of them. New failure modes get caught and
   recorded against their repository.

8. **Search-groups are config, not code** (D8). Adding a class of brand
   reference must never require a code change. If a feature seems to need a new
   hardcoded category, that is a signal the group model needs extending instead.

9. **String config comes from the scalar's source text** (`config/scalars.py`,
   D2/D3). PyYAML implements YAML 1.1, so `07654321` — a plausible company
   number — parses to `2054353`. Never coerce a config value with `str()`: build
   it from `scalar_text()`, which prefers the `raw` source text. Getting this
   wrong searches hundreds of repositories for a number that appears in none of
   them and reports them all clean, which is invariant 6 in disguise.

   `bool` is deliberately **not** wrapped. Python forbids subclassing it, so a
   raw-carrying bool would have to subclass `int`, at which point
   `isinstance(x, bool)` is false for it — `include_archived: true` would be
   rejected and `similarity_threshold: true` would be accepted as `1`. Do not
   "finish the job" by wrapping it.

10. **One model behind all three summary renderings** (`report/summary_model.py`,
    D1). Markdown, HTML and the JSON sidecar all render `SummaryModel`. No
    renderer aggregates anything itself and none derives its content from
    another's output, because the contract is that the forms agree — a reader
    who opens the HTML must not be reading a different run from the one who
    opens the Markdown. Adding a section means adding it to the model and to
    each renderer, never computing it inside one of them.

11. **Repository content is escaped on the way into a report** (D6). A matched
    excerpt is whatever hit a regex in someone else's repository: `<script>` in
    a template, a pipe in a Markdown file, a backtick in a shell script. HTML
    escapes it; Markdown escapes the pipe. Unescaped, the row is wrong without
    looking wrong.

12. **Confidence bands are absolute in distance** (`config/model.py`, D2/D3).
    "Very high" must mean the same thing in every run and on both hosts, so the
    ladder is fixed in perceptual-hash distance rather than scaled to the
    configured threshold. A band wholly beyond the threshold is omitted — it
    could never hold a finding — but a reachable empty band is kept, because
    `low: 0` at threshold 10 says every image match was a solid one.

13. **A run's artifacts are per-run; the clones are not** (`paths.py`, D1/D5).
    Reports, all three summaries, the checkpoint, the log and the run record
    hang off `run_dir`; only `clones_dir` hangs off `root`. The split is the
    whole point of the change that introduced it — a finished run must survive
    the next one, or there is nothing to compare against. The clones are
    deliberately outside it: they are working copies rather than evidence, they
    are the bulk of the tree, and invariant 4 draws the hard-reset boundary
    around exactly one of them. What a run actually saw in a clone is pinned by
    the `commit_sha` in its reports, which is what makes two runs comparable.

14. **The run record carries no totals** (`run_record.py`, D3). It answers
    *which run is this and did it finish* — the second half is what makes
    resumption decidable at all. It must never grow a finding count or any
    other rollup figure: that is invariant 10's problem restated, a second
    statement of the same numbers computed at a different point in the run and
    free to disagree with the summary. Cross-run comparison reads
    `executive-summary.json`.

## Working on this

- **The spec leads.** `openspec/specs/` is the current contract. For a behaviour
  change, raise a change and write its delta spec under
  `openspec/changes/<name>/specs/` first, then the code. A delta that modifies an
  existing requirement must carry the **whole** requirement block copied from
  `openspec/specs/`, scenarios included — a partial MODIFIED silently drops the
  scenarios it omits. Use `/opsx:apply` to work through `tasks.md` and tick each
  `- [ ]` → `- [x]` **as it is verified by a passing test**, not when the code is
  merely written.
- **Keep the OpenSpec documentation current as work is archived.** Archiving a
  change is what moves its behaviour into `openspec/specs/`, so nothing may be
  archived while its deltas are unsynced. When you archive, in the same pass:
  sync the deltas into `openspec/specs/`, run
  `openspec validate --specs --strict`, and update this file — the test count,
  the Outstanding section, and any path that pointed into the change directory
  you just moved under `archive/`. Stale guidance here is worse than none: it is
  read as current by the next session.
- **Every requirement has a test.** The suite is organised around spec
  scenarios, not around functions. A new requirement without a test that would
  fail before it is not done.
- **External processes are wrapped.** All `gh` and `git` invocation goes through
  `acquisition/commands.py` so failures arrive as typed errors with stderr
  attached. Do not call `subprocess` directly elsewhere.
- **British spelling** in user-facing strings and identifiers (`colour`,
  `rasterise`, `organisation`) — matches the specs and the existing code.

## Git working practice

- **A new session starts a new branch.** Never commit to `main`. Branch with
  `git checkout -b <name>` — or take a worktree when the work needs to sit
  alongside another branch rather than replace it in the working directory.
- **Commit as you go**, not in one lump at the end. A commit per coherent step,
  with the tests passing at that point — so a bisect lands somewhere useful and
  a bad step can be dropped without unpicking the good ones around it.
- **Push the branch when the work is finished**, and open a PR from there. Do
  not merge to `main` locally.

## Outstanding

`per-run-output-directories` is **implemented but not archived**, so its
behaviour is not yet in `openspec/specs/` and `openspec list` reports it as
active. Archiving it is the next step: sync `run-output-layout` (a seventh
capability) and the modified `repository-acquisition` requirement, then update
the invariant preamble above, which currently points at the live change
directory. Everything in it was verified against synthetic fixtures; nobody has
yet taken two runs over the real estate and compared them.

The four changes before it are implemented and recorded in `openspec/specs/` —
six capability specs, the source of truth from here on.

The scanner's own last open items (tasks 8.1, 8.3, 8.4) were verified against
the operator's real environment on 2026-07-31: the validation set was
assembled, the similarity threshold was confirmed empirically at the documented
default of 10, and a per-repo `report.md` was confirmed to ingest cleanly as fix
instructions for an AI coding agent. Everything else was verified against
synthetic fixtures.

`accept-numeric-config-scalars` (archived 2026-07-31) added invariant 9 above:
a bare company number in `brand.legal` no longer needs quoting, and every
string-valued config position is now built from the scalar's source text. Two
requirements were added to `scan-configuration`. Verified against synthetic
fixtures, including an end-to-end scan of a repository carrying `07654321`.

`enrich-executive-summary` (archived 2026-07-31) added invariants 10–12 above.
The executive summary now carries each row's configured severity, expands
search-group rows into the values that actually matched, bands image findings
by likeness confidence, and is written as `executive-summary.html` alongside
the Markdown and the JSON. Two requirements were added to `executive-summary`
and one modified. Verified against synthetic fixtures, and the rendered HTML
was confirmed in a browser by the operator on 2026-07-31.

`per-run-output-directories` (implemented 2026-07-31) added invariants 13–14
above. Every run now writes into its own `YYYY-MM-DD-HHMMSS-run` directory
under the output root, so a re-run no longer overwrites the run before it;
clones stay shared at the root. An unfinished run is continued by re-running
the same command, a finished one is left alone in favour of a new run, and
`--run-id` names one outright. One capability was added and one requirement in
`repository-acquisition` modified.
