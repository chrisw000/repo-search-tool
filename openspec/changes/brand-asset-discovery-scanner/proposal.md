# Brand Asset Discovery Scanner

## Why

A brand change must be applied across ~400 repositories spread over two GitHub instances (one GitHub Enterprise Server, one github.com cloud, each behind its own SSO). The old brand's assets are scattered under unknown filenames and paths, in many image formats and sizes, sometimes recoloured, sometimes inlined as base64 in code, sometimes embedded in markup. Filename search misses most of this.

We need a single automated tool that:

- Discovers where the old brand lives by **content** (image similarity) and by **text pattern** (names, fonts, domains, colours, legal strings), not by filename.
- Runs unattended across hundreds of repos on both hosts, resumably and with per-repo failure isolation.
- Produces **one report per repository** written as actionable fix-instructions, plus **one executive summary** across all repos.

The per-repo reports are the hand-off: they are fed to an AI coding agent later to perform the actual fixes. This tool finds and reports only — it does not fix.

**POC context.** This greenfield CLI is the *mechanics* run for evaluating OpenSpec's loop (propose → review → apply) on a self-contained tool with no legacy noise. It deliberately encodes the non-obvious image-matching decisions (see `design.md`) so we can watch whether editing-the-spec-then-regenerating beats editing-code, and whether generated code stays traceable to requirements. It is not a substitute for the dependency-remediation pilot, which carries the compliance/traceability surface this task lacks.

## What Changes

Six new capabilities, all additive — this is a greenfield CLI and no existing code is touched.

- **Repository acquisition.** Enumerate and shallow-clone repos across multiple `{host, org}` targets. Resumable via checkpoint, with per-repo failure isolation so one bad repo cannot end the run. Resolve each repo's *real* default branch rather than assuming `main`. Refresh already-cloned repos to current HEAD. Accept user-supplied pre-cloned directories and treat them non-destructively.
- **Scan configuration.** One declarative config file. Text search is modelled as named, extensible **search-groups** (patterns + file-glob scope + severity) rather than hardcoded categories, so adding a new class of match is config-only. A folder of **labelled** reference images, a tunable similarity threshold, and scope defaults.
- **Text-pattern search.** Execute search-groups across in-scope files, capturing path, line, and surrounding context. Coverage spans brand names (including inside markup: alt text, CSS class names, SVG titles), font names and references, legacy domains, brand hex/rgb colours, legal and trademark strings, and base64-embedded images.
- **Image-similarity search.** Content-based matching independent of filename, format, and size. Trim to the content bounding box before hashing, then hash in grayscale so colourways collapse to one reference per layout. Covers raster formats, `.ico`, SVG (rasterised), and base64-decoded images.
- **Per-repository reporting.** One Markdown report per repo, written to be ingested by an AI coding agent, plus a JSON sidecar. Findings carry type, matched group or reference label, path, line, severity, a permalink, and a provenance block. Clean repos and skipped repos are reported explicitly rather than omitted.
- **Executive summary.** One cross-repo rollup: totals, repositories ranked by remediation weight, breakdown by match type and severity, and drill-through links into the per-repo reports.

## Capabilities

### New Capabilities

- `repository-acquisition`: Multi-host authenticated enumeration and cloning of target repositories, resumable and failure-isolated, covering managed clones and non-destructive external clones.
- `scan-configuration`: The declarative configuration contract — search-group model, labelled reference-image set, similarity threshold, and file-scope defaults.
- `text-pattern-search`: Execution of configured search-groups over in-scope files, including markup-aware and base64-aware coverage.
- `image-similarity-search`: Filename-independent image matching by perceptual hash, with bounding-box trimming, grayscale normalisation, and a pluggable matching strategy.
- `per-repository-reporting`: The per-repo Markdown report and JSON sidecar, their finding schema, and their provenance block.
- `executive-summary`: The cross-repository rollup and triage ranking.

### Modified Capabilities

None. `openspec/specs/` is empty; this change introduces the first capabilities in the project.

## Impact

- **Affected specs:** six new capabilities, all `ADDED` — `repository-acquisition`, `scan-configuration`, `text-pattern-search`, `image-similarity-search`, `per-repository-reporting`, `executive-summary`.
- **Affected code:** a new standalone CLI tool. No existing repositories or code are modified by this change. The ~400 scanned repositories are read-only inputs.
- **External dependencies:** the `gh` CLI (authenticated per host), `git`, an image library for decoding and perceptual hashing, and an SVG rasteriser.
- **Out of scope (phase 1, by design):**
  - Auto-fixing findings — that is the later AI-agent step.
  - Git history and deleted commits — a rebrand cares about current HEAD.
  - Non-default branches — default branch only.
  - Cross-run diffing.
- **Deferred to phase 2 (seam designed in phase 1, not built):**
  - Composite/embedded-logo matching, for logos sitting beside other content within a larger image.
  - Colourway detection, reporting *which* colour variant matched.
  - Image extraction from PDF and Office documents.
  - A perceptual-hash cache keyed by content hash.
