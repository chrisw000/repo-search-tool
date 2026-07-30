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

# Tests — full suite is ~45s, currently 141 passing.
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
openspec/changes/   the specifications this was built from
```

## Load-bearing invariants

Do not "simplify" these away. Each encodes a decision recorded in
`openspec/changes/brand-asset-discovery-scanner/design.md`.

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

- **The spec leads.** For a behaviour change, update the relevant capability
  spec under `openspec/changes/.../specs/` first, then the code. Use
  `/opsx:apply` to work through `tasks.md` and tick each `- [ ]` → `- [x]`
  **as it is verified by a passing test**, not when the code is merely written.
- **Every requirement has a test.** The suite is organised around spec
  scenarios, not around functions. A new requirement without a test that would
  fail before it is not done.
- **External processes are wrapped.** All `gh` and `git` invocation goes through
  `acquisition/commands.py` so failures arrive as typed errors with stderr
  attached. Do not call `subprocess` directly elsewhere.
- **British spelling** in user-facing strings and identifiers (`colour`,
  `rasterise`, `organisation`) — matches the specs and the existing code.

## Outstanding

Tasks 8.1, 8.3, and 8.4 in
`openspec/changes/brand-asset-discovery-scanner/tasks.md` are unticked and need
the operator's real environment: assembling a validation set of 5–6
representative repositories, tuning the similarity threshold against it, and
confirming a per-repo `report.md` ingests cleanly as fix instructions for an AI
coding agent. Everything verified so far used synthetic fixtures.
