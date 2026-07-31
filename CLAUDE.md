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

# Tests — full suite is ~55s, currently 260 passing.
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
  paths.py          output layout, namespaced host/org/repo
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
and invariants 10–12, whose decisions live in
`openspec/changes/enrich-executive-summary/design.md` — move that path when the
change is archived.

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

Nothing. All three changes are implemented and their behaviour is now recorded
in `openspec/specs/` — six capability specs, the source of truth from here on.

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

`enrich-executive-summary` is **active, implemented, not yet archived**. It
added invariants 10–12 above. The executive summary now carries each row's
configured severity, expands search-group rows into the values that actually
matched, bands image findings by likeness confidence, and is written as
`executive-summary.html` alongside the Markdown and the JSON. Two requirements
were added to `executive-summary` and one modified.

Its one open item is task 8.3: the generated HTML has been verified
structurally — every section present, every drill-through link resolving, no
external reference, every band and severity naming itself in text — but has not
yet been opened in a browser against a real run. Do that before archiving, then
sync the deltas into `openspec/specs/` and update this file.
