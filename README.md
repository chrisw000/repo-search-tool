# repo-search-tool

`brandscan` — a brand asset discovery scanner. It finds where an old brand still
lives across hundreds of repositories, by **image content** and by **text
pattern**, and writes one remediation report per repository plus one executive
summary across all of them.

It finds and reports only. It never edits a scanned repository.

## Why content matching

Filenames across a large estate are unreliable — `logo.png`, `header-2.svg`,
`sprite.png`, or no filename at all when the image is inlined as base64. So
images are matched by perceptual hash over trimmed luminance, which means a copy
that has been renamed, reformatted, resized, recoloured, or padded still
matches. The reference set needs one image per *layout* (horizontal, stacked,
icon, wordmark), not one per colourway.

The known blind spot: a logo composited inside a larger image (a banner, a
screenshot) is not detected, because the surrounding content dominates the
signature. The matching strategy sits behind an interface so a sub-region
strategy can be added without disturbing anything else.

### What counts as a match

Both images are trimmed to their content and resized onto a fixed 32×32 grid
before hashing, so most of what varies between two copies of a logo is
discarded before comparison. Measured distances against the default threshold
of 10 (lower is closer):

| Difference | Effect | Matches? |
|---|---|---|
| Filename and path | none | ✅ |
| Pixel size, 48×24 up to 2400×1200 | distance 0–6 | ✅ |
| Aspect ratio, even 2:1 vs 5:1 | distance 0–2 | ✅ |
| Lossless re-encoding (PNG↔GIF↔BMP↔WEBP↔TIFF) | distance 0 | ✅ |
| JPEG at q75–q95 | distance 0–6 | ✅ |
| Recolouring | distance 0–4 | ✅ |
| Transparent or solid padding | distance 0–2 | ✅ |
| SVG rasterised against a raster twin | distance 6 | ✅ |
| A different *layout* (stacked vs horizontal) | distance ~36 | ❌ correctly |
| Unrelated image or noise | distance 30+ | ❌ correctly |
| JPEG below ~q25 **and** small (<100px) | distance 14–30 | ⚠️ missed |

Two consequences worth internalising:

- **Proportions carry no information.** A squashed or stretched copy still
  matches, which is what you want — but it also means two reference images
  differ only if their elements are *arranged* differently. A stacked lockup
  and a horizontal one qualify; the same lockup in a taller frame does not.
- **Only loss of detail breaks matching.** Heavy JPEG compression on a small
  image is the one realistic failure. If your estate has a lot of those,
  consider a threshold nearer 15 — but check it against genuine non-matches
  first, since those sit at 30+ and that is the headroom you are spending.

---

## 1. Prerequisites

| Tool | Why | Check |
|---|---|---|
| Python 3.11+ | the tool itself | `python --version` |
| `git` | cloning and reading repositories | `git --version` |
| [`gh`](https://cli.github.com) | enumerating organisations on each host | `gh --version` |

## 2. Build

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Verify the install:

```powershell
.\.venv\Scripts\brandscan.exe --version      # -> brandscan 0.1.0
.\.venv\Scripts\python.exe -m pytest -q      # -> 141 passed
```

SVG rasterisation pulls `rlPyCairo` and `pycairo`. Both install from wheels on
Windows with no native Cairo build. If they ever fail, SVGs are reported as
unreadable files rather than silently skipped — everything else still runs.

## 3. Authenticate

**Each host needs its own session.** A GitHub Enterprise Server instance and
github.com are separate SSO boundaries; credentials are not interchangeable.

```powershell
gh auth login --hostname github.com
gh auth login --hostname ghes.your-company.example
```

If an organisation enforces SAML SSO, a valid token still has to be *authorised*
for that organisation. Check each one enumerates before you commit to a long run:

```powershell
gh auth status --hostname github.com
gh api --hostname github.com "orgs/<your-org>/repos?per_page=1"
```

If that second command returns 403 with an SSO message, authorise the token for
the organisation (GitHub shows a link in the error, or use
`gh auth refresh --hostname <host> -s read:org,repo`).

You do not have to get this right by hand — `brandscan` runs the same check for
every configured host and organisation before it clones anything, and aborts
with a per-host remedy if any of them fails. That preflight exists so you find
out in the first ten seconds rather than on repository 200 of a multi-hour run.

## 4. Configure

```powershell
Copy-Item config.example.yaml config.yaml
```

Then edit `config.yaml`. For a straightforward rebrand the only block you need
to touch is `brand:` — the six default search-groups (brand names, font names,
font references, legacy domains, brand colours, legal strings) are built from
it. Adding a new class of brand reference is a configuration change, never a
code change.

A company or VAT number can be written as a bare numeral — `07654321` — with no
quoting. It is searched for exactly as you wrote it, leading zero included.

You also need a folder of reference logos:

```
references/
  logo-horizontal.png
  logo-stacked.png
  icon.png
  wordmark.svg
  labels.yaml          # or use reference_images.labels in config.yaml
```

Every reference must carry a label naming the layout it represents. An
unlabelled one fails validation by name, rather than quietly acquiring a
filename-shaped label.

Two scope defaults are deliberate and worth knowing:

- Dependency directories (`node_modules`, `vendor`, …) are **excluded**.
- Build output (`dist`, `build`, `bin`, `wwwroot`, …) is **not excluded**.
  Deployed brand assets frequently exist only there. The cost is some duplicate
  findings between source and build output; the alternative is silently missing
  the assets that actually ship.

`config.yaml` and `references/` are gitignored by default, since they name
internal hosts and usually hold proprietary artwork.

## 5. Initial checks

Work up in three steps rather than pointing it at 400 repositories cold.

```powershell
# a. Configuration only — validates and exits, acquires nothing.
.\.venv\Scripts\brandscan.exe validate-config --config config.yaml

# b. Auth preflight plus a chosen handful of repositories.
.\.venv\Scripts\brandscan.exe scan --config config.yaml `
    --repo contoso/legacy-webforms `
    --repo contoso/checkout-ui `
    --repo contoso/brand-assets

# c. Read what came out before scaling up. Each run writes its own dated
#    folder, so this is the newest one.
code (Get-ChildItem .\brandscan-output\*-run | Sort-Object Name)[-1]\executive-summary.md
```

**Choose the trial set deliberately.** Include at least one legacy repository
whose default branch is not `main`, and one with checked-in build output —
those are the cases most likely to hold stale branding and most likely to
surface a problem with the tool. `--limit 5` exists, but it takes whichever
five come first alphabetically, which is not a validation set.

`--repo` is repeatable and takes `ORG/NAME` to narrow a configured target, or
`HOST/ORG/NAME` to name one outright. The same subset can live in the config
instead, as `repos:` under a target. Either way the named repositories are
fetched directly rather than by paging through the organisation, and a name
that does not resolve is reported as a failure rather than silently dropped —
a trial that quietly scans four of five would be worse than useless.

Note that a trial via `--external-root` instead exercises the *external* clone
path, which is read-only. Your full run uses managed clones — shallow clone,
fetch, hard reset, origin guard — so a trial that never touches that path
leaves the riskier code untested.

At step (c), check three things:

1. **Are the image matches right?** If real logos are being missed, raise
   `similarity_threshold`; if unrelated images are matching, lower it toward 5.
   Whatever you settle on is recorded in every report's provenance block.
2. **Is the text noise tolerable?** Retune a group's `severity`, narrow its
   `include` globs, or drop it via `disable_search_groups`.
3. **Does a per-repo `report.md` read as usable fix instructions?** That is the
   whole purpose of the tool — it is handed to an AI coding agent to perform the
   fixes — and it is the most expensive thing to discover late.

## 6. Full run

```powershell
.\.venv\Scripts\brandscan.exe scan --config config.yaml
```

Useful flags:

| Flag | Effect |
|---|---|
| `--mode managed\|external\|both` | which acquisition posture to use (default `both`) |
| `--repo ORG/NAME` | scan only this repository; repeatable. `HOST/ORG/NAME` also accepted |
| `--external-root <dir>` | treat each git repo under a folder as an external clone |
| `--threshold N` | override the similarity threshold for this run |
| `--limit N` | stop after N repositories |
| `--refresh` | re-acquire and re-scan repositories an earlier run completed |
| `--no-resume` | ignore the checkpoint entirely |
| `--run-id NAME` | write to this run folder, rather than choosing one |
| `--skip-preflight` | skip the auth check (offline testing only) |
| `--verbose` | debug-level logging |

A run is resumable: progress is checkpointed after every repository, so an
interrupted run picks up where it stopped. Interrupt with Ctrl-C and re-run the
same command — an unfinished run is continued in place.

Once a run has finished, re-running the same command starts a **new** run
folder rather than reopening the finished one, so the earlier run's reports
survive to be compared against. `--refresh` and `--no-resume` likewise start a
new run. To add to or redo a specific earlier run instead, name it:
`--run-id 2026-07-31-142530-run`.

Exit codes: `0` clean run, `1` completed with failures or run-level errors,
`2` configuration error, `3` authentication preflight failed.

## Output

```
brandscan-output/
  clones/<host>/<org>/<repo>/     # managed shallow clones (reset on re-run)
  2026-07-31-142530-run/          # one folder per run, UTC, sorts by date
    executive-summary.md          # totals, triage order, breakdowns
    executive-summary.html        # the same document, browsable
    executive-summary.json
    run.json                      # which run this is, and whether it finished
    checkpoint.json               # resumability
    run.log.jsonl                 # structured run log, one JSON object per line
    reports/<host>/<org>/<repo>/
      report.md                   # the hand-off: fix instructions
      report.json                 # machine-readable sidecar
  2026-08-04-090113-run/          # the next run, left to compare against
    ...
```

Everything a run produces sits in its own folder, so a later run never
overwrites an earlier one's evidence. The clones are the exception: they are
working copies rather than results, shared between runs and always reset to the
current default-branch tip, and what a run actually saw in one is pinned by the
commit recorded in its reports.

Run folders accumulate — nothing prunes them. Delete the ones you no longer
want to compare against.

Every report carries a provenance block — search-groups executed, reference
labels searched, similarity threshold, scanned commit and branch, timestamp,
tool version — so a stale report is distinguishable from a fresh one. Clean,
skipped, and failed repositories each get a report; "no findings" is never
confused with "never scanned".

Tail a long run with:

```powershell
# The run folder is printed when the scan starts; paste it in here.
Get-Content .\brandscan-output\2026-07-31-142530-run\run.log.jsonl -Wait -Tail 20
```

## Safety

- **Managed clones**, under `clones/`, are fetched, hard-reset, and cleaned on
  every run. An origin-URL guard records a mismatched directory as an
  acquisition failure rather than resetting it.
- **External clones** you point the tool at are never modified. A clean one is
  scanned where it stands; a **dirty** one is skipped with the reason recorded,
  rather than reset over your uncommitted work.

---

## OpenSpec installation and setup

This repository is also the mechanics run for evaluating OpenSpec's
propose → review → apply loop. See `openspec/changes/` for the specifications
the tool was built from.

https://github.com/Fission-AI/OpenSpec

```bash
# install openspec
pnpm install -g @fission-ai/openspec@latest

# check the installation
openspec --version

OPENSPEC_TELEMETRY=0

# create the openspec/ directory, configuration files, and AGENTS.md.
openspec init

# Quick start after setup:

# Start a change
/opsx:propose "your idea" (Claude Code)
/opsx-propose "your idea" (GitHub Copilot)

# Implement tasks
/opsx:apply
```
