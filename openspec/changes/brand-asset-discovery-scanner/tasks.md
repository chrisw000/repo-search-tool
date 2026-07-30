# Tasks — Brand Asset Discovery Scanner

## 1. Project scaffold

- [x] 1.1 CLI entry point and argument parsing, including the flags selecting managed vs external-clone mode
- [x] 1.2 Output-directory bootstrap, namespaced by host / organisation / repository
- [x] 1.3 Structured logging and run-progress reporting (per-repo start and finish, running counts)
- [x] 1.4 Tool version exposed to reporting, for the provenance block

## 2. Configuration

- [x] 2.1 Config file loader with schema validation; abort before any acquisition and name the offending field
- [x] 2.2 Search-group model: name, patterns, include/exclude globs, severity — extensible by config alone, no code change
- [x] 2.3 Seed the default groups: brand-names, font-names, font-references, legacy-domains, brand-colours, legal-strings
- [x] 2.4 Reference-image folder loader with per-image layout labels; fail validation naming any unlabelled reference
- [x] 2.5 Global scope defaults: exclude dependency directories, do NOT exclude build output (D9); all overridable
- [x] 2.6 Similarity threshold config with documented default (~10), recorded in provenance when defaulted

## 3. Repository acquisition

- [x] 3.1 Multi-host auth preflight: per host confirm an authenticated session AND that each target org is enumerable; abort with a per-host remedy naming the host
- [x] 3.2 Org enumeration across {host, org} targets with full pagination (no truncation past ~400 repos)
- [x] 3.3 Archived/fork inclusion flags, both off by default
- [x] 3.4 Resolve each repository's actual default branch — never assume `main` (D5)
- [x] 3.5 Managed shallow clone of the default branch into the tool's own directory; record the acquired commit SHA
- [x] 3.6 Managed-clone refresh: fetch, hard-reset to default-branch tip, clean untracked files
- [x] 3.7 Origin-URL guard: a managed directory not matching the intended repository is recorded as an acquisition failure, never reset
- [x] 3.8 External pre-cloned mode, non-destructive: clean → scan as-is at current commit and record the SHA; dirty → skip with recorded warning (D6)
- [x] 3.9 Per-repo failure isolation — one failed repository records its reason and the run continues
- [x] 3.10 Run checkpointing for resumability; on resume, skip already-completed repositories

## 4. Text-pattern search

- [x] 4.1 File walker honouring global scope plus each group's own include/exclude globs
- [x] 4.2 Execute each search-group over in-scope files; capture relative path, line number, group name, severity, and context lines
- [x] 4.3 Markup-aware coverage: image alt attributes, CSS class and identifier names, SVG title/description elements
- [x] 4.4 Font coverage: font-family and font-face declarations, embedded font file extensions, external font-service links
- [x] 4.5 Legacy domain and URL coverage
- [x] 4.6 Brand colour coverage across equivalent notations (hexadecimal and functional forms of the same colour)
- [x] 4.7 Legal and trademark string coverage
- [x] 4.8 Base64 `data:` image URI discovery: decode and hand off to image matching; skip undecodable payloads without ending the file or repository scan

## 5. Image-similarity search

- [x] 5.1 Image enumeration: raster formats, icon containers, vector images, and base64-decoded payloads
- [x] 5.2 Content bounding-box trim — alpha padding and solid-colour padding, with fuzz tolerance for anti-aliased edges
- [x] 5.3 **Enforce trim-before-mode-conversion ordering** (D2) — converting first yields a full-frame alpha channel and silently disables the trim
- [x] 5.4 Grayscale perceptual hash and distance computation against the labelled reference set (D3)
- [x] 5.5 Vector rasterisation to a fixed canvas, feeding the same hash pipeline; isolate per-file rasterisation failures
- [x] 5.6 Threshold-governed match decision; record matched reference label and measured distance; order multi-reference matches by increasing distance
- [x] 5.7 Isolate the matching strategy behind an interface so a sub-region strategy can be added later without touching acquisition, config, or reporting (D4)
- [x] 5.8 Skip undecodable images with the failure recorded, without ending the repository scan

## 6. Per-repository reporting

- [x] 6.1 Markdown report per repository, presenting grouped actionable fix instructions rather than a raw match dump
- [x] 6.2 JSON sidecar carrying the same findings, with no finding omitted relative to the Markdown
- [x] 6.3 Finding schema: match type, matched group name or reference label, relative path, line, severity, and image distance where applicable
- [x] 6.4 Permalink construction per host, pinned to the scanned commit SHA and line
- [x] 6.5 Provenance block: groups executed, reference labels searched, threshold used, scanned SHA and branch, timestamp, tool version
- [x] 6.6 Report clean repositories explicitly as clean; report skipped and failed repositories with their reason and never as clean
- [x] 6.7 Confirm every target repository has a report, including skipped and failed ones

## 7. Executive summary

- [x] 7.1 Aggregate run totals: scanned, clean, with-findings, skipped/failed — reconciling against the full target set
- [x] 7.2 Remediation-weight ranking, severity dominating raw count, heaviest first
- [x] 7.3 Breakdown by search-group and reference label across all repositories
- [x] 7.4 Breakdown by severity across all repositories
- [x] 7.5 Drill-through links from each listed repository to its own report, including skipped ones with the reason visible

## 8. Validation

- [ ] 8.1 Assemble a validation set of 5–6 representative repositories, deliberately including one legacy repo with a non-`main` default branch and one with checked-in build output
- [x] 8.2 Verify content-based matching survives rename, reformat, resize, recolour, and padding
- [ ] 8.3 Tune the similarity threshold empirically against the validation set and record the settled default
- [ ] 8.4 Confirm the per-repo Markdown ingests cleanly as fix instructions for an AI coding agent before scaling to ~400
- [x] 8.5 Exercise resumability and per-repo failure isolation with a deliberately interrupted run
- [x] 8.6 Verify the non-destructive external-clone path leaves a dirty working copy untouched
