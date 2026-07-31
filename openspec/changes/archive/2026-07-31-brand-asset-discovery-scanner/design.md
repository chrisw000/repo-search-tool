# Design — Brand Asset Discovery Scanner

## Context

See `proposal.md` — Why. Constraints that shape the approach:

- **Two hosts, two SSO boundaries.** One GitHub Enterprise Server, one github.com. Credentials, org membership, and authorisation differ per host and are not interchangeable.
- **Scale forces unattended operation.** ~400 repositories means a run measured in hours. Anything that halts the run on a single bad repository is unusable, and anything that cannot resume wastes the whole run on an interruption.
- **The estate is old.** It includes WebForms-era code. Legacy conventions — non-`main` default branches, checked-in build output, vendored assets — are the norm rather than the exception, and those repositories are the ones most likely to carry stale branding.
- **The consumer is a machine.** The per-repo report is fed to an AI coding agent to perform fixes. Its structure is therefore a contract, not a presentation choice.

Most of this tool's value sits in a handful of non-obvious matching decisions. They were reached by reasoning about *how brand assets actually hide in repositories*, not from the surface request. Recorded here so that the spec, rather than the implementation, is their home — which is precisely what the POC is testing.

## Goals / Non-Goals

**Goals:**

- Detect brand residue by content and by pattern across both hosts, unattended.
- Make the matching subtleties explicit enough that a regenerated implementation stays correct.
- Keep the six capabilities separable, so the matching strategy can be replaced without touching acquisition, configuration, or reporting.
- Emit per-repo fix instructions and one executive rollup.

**Non-Goals:**

- Fixing anything. See `proposal.md` — Impact for the full scope boundary.
- Design-level: no attempt at sub-region logo detection in this phase, no caching layer, and no cross-run state beyond the resumability checkpoint.

## Decisions

### D1. Match by content, not by filename

Filenames across this estate are unreliable — `logo.png`, `header-2.svg`, `sprite.png`, or no filename at all when the image is inlined as base64. Detection is therefore by image content similarity and by text pattern.

*Alternative considered:* filename and path heuristics as the primary signal. Rejected — it is exactly the approach that already fails, and it would produce a confidently incomplete report, which is worse than an obviously incomplete one. Filename is admissible only as a weak signal folded into an ordinary search-group.

### D2. Trim to the content bounding box before hashing — and before mode conversion

Perceptual hashing normalises the *whole frame* to a fixed grid. The same logo at 100% and at 60% inside transparent padding lands its features in different grid cells and yields a different signature. Trimming both reference and candidate to the content bounding box removes this.

Handling: transparent padding gives a bounding box from the alpha channel; solid-colour padding gives one from the difference against the corner pixel colour; anti-aliased or near-uniform borders need a small fuzz tolerance so faint edges do not defeat the trim.

**The ordering is load-bearing.** Trim on the freshly opened image *before* any colour-mode conversion. Converting an opaque image to RGBA first gives it a full-frame alpha channel, after which it never trims — the operation silently becomes a no-op and matching quietly degrades. This is the single easiest thing to get wrong when regenerating the implementation, which is why it is stated as a requirement rather than left to the code.

### D3. Hash in grayscale — one reference per *layout*, not per colourway

Perceptual hashing over luminance is colour-blind by construction: two logos identical in shape but different in colour produce the same hash.

Two consequences, both wanted:

- The reference set needs one image per distinct **layout** (horizontal, stacked, icon-only, wordmark), not one per colourway. The known variants collapse to a much smaller set.
- Recoloured copies nobody catalogued are caught for free — which, for a rebrand, is the entire point.

Exact same-format copies are subsumed at distance 0, so no separate cryptographic-hash pass is needed for detection.

*Alternative considered:* colour-aware hashing, to report which colourway matched. Rejected for phase 1 — it multiplies the reference set, and it inverts the priority by making uncatalogued recolours *harder* to find. Colourway detection is deferred.

### D4. Composite logos are the known blind spot — isolate the seam now

When a logo is composited into a larger image — a banner with a tagline, a screenshot, a hero image — the whole-image hash is dominated by everything around the logo and will not match a clean reference however well trimmed. This is a real limitation, not a tuning problem, and no threshold setting fixes it.

Detecting a logo as a *sub-region* needs feature or template matching. That is deferred to phase 2, but the phase-1 matching strategy sits behind an interface so the sub-region strategy plugs in without disturbing acquisition, configuration, or reporting.

Note for phase 2: flat minimal wordmarks throw few keypoints, so keypoint-based approaches underperform on exactly this logo class; edge-based multi-scale template matching is the more reliable fallback. The seam must therefore not assume a single strategy.

### D5. Resolve the real default branch — never assume `main`

Legacy repositories commonly default to `master`, occasionally `develop` or `trunk`. Those legacy repositories are precisely the ones most likely to hold stale branding, so hardcoding `main` would blind the tool exactly where it matters most — and would fail silently, as an empty scan rather than an error.

### D6. Managed and external clones get different safety postures

- **Managed clones**, in the tool's own directory: on re-run, fetch then hard-reset to the default-branch tip and clean untracked files. Safe because nobody works there, and it guarantees the scan reflects current HEAD. Incremental fetch is fast; only the first clone is slow. Shallow throughout — no history is needed.
- **External pre-cloned directories**, where the user points at their own working copies: never mutate. A clean external clone is scanned as-is at its current commit, with the SHA recorded so staleness is visible. A **dirty** external clone is **skipped with a recorded warning** — silently hard-resetting over someone's uncommitted work is unacceptable, and is not a trade-off worth any amount of coverage.

An origin-URL guard rejects a managed directory that does not correspond to the intended repository, recording it as an acquisition failure rather than resetting whatever happens to be sitting there.

### D7. Multi-host auth preflight — fail early, not on repository 200

Two hosts, each behind SSO. The `gh` binary being installed proves nothing, and a token can be valid yet not SSO-authorised for a given org.

So the preflight verifies, per host, both that an authenticated session exists *and* that each target org can actually be enumerated. It aborts before any cloning with a per-host remedy naming the host. The alternative — discovering the problem partway through a multi-hour run — wastes the run and the operator's attention.

### D8. Named, extensible search-groups over hardcoded categories

Model text search as named groups, each with its own patterns, file-glob scope, and severity. Seeded defaults: brand names, font names, font references, legacy domains, brand colours, legal strings.

Adding a new group is config-only. Same engine, and it generalises into the org-wide scanner the team will inevitably want to point at other things.

*Alternative considered:* hardcoded categories matching the six named in the request. Rejected — the categories in the request are examples of a general shape, not a closed set, and hardcoding them would force a code change for the first pattern nobody anticipated.

### D9. Scope defaults with a build-output carve-out

Exclude dependency directories (`node_modules`, `vendor`) by default. Do **not** blanket-exclude `dist` or `build` — deployed brand assets frequently exist *only* in build output, and excluding it would create silent misses of exactly the assets that are actually shipped. The cost is some duplicate findings between source and build output; that is a much better failure than a confident miss.

### D10. Reporting is a contract, not an afterthought

The per-repo report is the artifact fed to an AI agent for fixes, so its structure is a requirement. Markdown-primary and agent-ingestible, presenting actionable findings rather than a raw match dump, with a JSON sidecar for machine consumption.

Three properties earn their place:

- **Severity** per finding — a logo image is high, a legacy domain or legal string medium, a lone brand mention in a comment low. This is what makes the executive summary a triage list instead of a leaderboard.
- **Permalink** per finding, to the host blob at the scanned commit SHA and line — so a report stays navigable after the branch moves on.
- **Provenance block** per report — groups and reference labels searched, similarity threshold, scanned SHA and branch, timestamp, tool version. Without it a report is unreproducible, and a stale report is indistinguishable from a fresh one.

Clean and skipped repositories are reported explicitly, so that "no findings" is never confused with "never scanned".

## Risks / Trade-offs

- **Perceptual-hash threshold is empirical.** → Start around 10; tighten toward 5 to cut noise, loosen to catch more. Expose it as config and settle it on the validation set rather than guessing up front. Record the value used in every report's provenance so results stay interpretable.
- **Composite/embedded logos are missed in phase 1 (D4).** → Accepted knowingly. Mitigated by the strategy seam, and by the fact that text-pattern search often catches the same asset by a different route (alt text, CSS class, surrounding markup).
- **SVG rasterisation adds a dependency and a failure surface.** → Rasterise to a fixed canvas; isolate failures per file so one malformed SVG cannot end a repository's scan.
- **Build-output inclusion (D9) inflates finding counts** where an asset appears in both source and build output. → Accepted; a duplicate is cheap to dismiss and a miss is not. Severity ranking keeps the summary useful despite the extra volume.
- **Grayscale hashing cannot say which colourway matched (D3).** → Accepted for phase 1; the agent performing fixes inspects the file anyway.
- **Hard-reset on managed clones destroys local state** in that directory. → Confined to the tool's own directory by the origin-URL guard, and never applied to user-supplied directories (D6).

## Migration Plan

Greenfield tool; nothing to migrate and nothing to roll back. Rollout is a validation step rather than a deployment:

Run against 5–6 representative repositories — deliberately including at least one legacy repository with a non-`main` default branch and one with checked-in build output — before pointing the tool at all ~400. This is the cheap moment to settle the similarity threshold and the report format, before either hardens. Confirm on that small set that the per-repo Markdown actually ingests cleanly as fix instructions for an AI agent, since that is the tool's whole purpose and the most expensive thing to discover late.

## Open Questions

- Where the severity boundary sits for a brand name appearing only in a code comment or a changelog entry — arguably low enough to be noise. Deferrable: severity is per search-group configuration, so this is a tuning call on the validation set and changes no spec, approach, or task.
- Whether the executive summary's remediation weight should treat a repository with one high-severity finding as heavier than one with many medium findings. Deferrable: the requirement fixes that severity dominates raw count; the exact weighting can be settled against real output.
