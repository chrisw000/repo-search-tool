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

# Tests — full suite is ~40s, currently 203 passing.
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
  config/           loader (field-named validation), model, seeded groups, references
  acquisition/      preflight, enumeration, clone/refresh, checkpoint, gh+git wrappers
  scan/             walker, text search, base64 extraction, image search driver
  images/           trim, hashing, SVG rasterisation, matching strategy seam
  report/           per-repo markdown + JSON sidecar, permalinks, executive summary
tests/              mirrors the above; conftest.py builds synthetic logos and git repos
openspec/specs/     the current behaviour contract — six capabilities, source of truth
openspec/changes/   in-flight changes; archive/ holds the ones already folded into specs/
```

## Load-bearing invariants

Do not "simplify" these away. Each encodes a decision (the `Dn` references
below) recorded in
`openspec/changes/archive/2026-07-31-brand-asset-discovery-scanner/design.md`.

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

Nothing. Both changes are implemented and their behaviour is now recorded in
`openspec/specs/` — six capability specs, the source of truth from here on.
Tasks 8.1, 8.3, and 8.4 were the last open items and were verified against the
operator's real environment on 2026-07-31: the validation set was assembled,
the similarity threshold was confirmed empirically at the documented default of
10, and a per-repo `report.md` was confirmed to ingest cleanly as fix
instructions for an AI coding agent. Everything else was verified against
synthetic fixtures.

Both changes are archived, so `openspec/changes/` holds only `archive/` and
`openspec list` reports no active changes. The next piece of work starts with a
new proposal.
