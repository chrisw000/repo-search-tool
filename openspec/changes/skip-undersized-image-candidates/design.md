## Context

See `proposal.md` — Why. The constraints that shape the approach:

- **Invariant 1** (`CLAUDE.md`): trim precedes any colour-mode conversion, and
  `signature_for()` fixes that order. Anything inserted into the load path has
  to sit outside it.
- **Invariant 5 / invariant 6**: build output stays in scope, and nothing that
  was not assessed may be reported as clean. This change removes candidates from
  assessment, so it owes an account of what it removed.
- **Invariant 8**: config, not code. The size and the exemptions are both data.
- **Invariant 10**: one model behind the three summary renderings. No renderer
  may learn about image sizes.
- `images/loader.py` is *the only place that decides why an input could not be
  read* (its own docstring). Its `_load` runs classify → decode → blank check.
- `ImageLoadError` carries an `UnreadableCause`, and every cause maps to a
  heading and a remediation in `findings.py`. The set is closed on purpose.

## Goals / Non-Goals

**Goals:**

- An image too small to carry a recognisable layout is not hashed, not matched,
  and not reported as anything.
- The threshold at which that applies is configurable and recorded.
- Favicons survive the cut at any minimum an operator chooses.
- What was skipped is visible in the report without being enumerated in it.

**Non-Goals:**

- Applying the minimum to *reference* images. A reference is a deliberate,
  labelled, validated choice by the operator; the minimum exists to filter
  incidental junk found in someone else's repository, and there is none of that
  in a reference folder. A too-small reference is a real hazard — it would sit
  near everything — but it is a configuration-validation question, and a
  separate one.
- Measuring the minimum against the *trimmed content* rather than the stored
  dimensions. See D2.
- Surfacing undersized counts in the executive summary. They are not findings,
  they do not rank a repository, and putting them there is invariant 10's cost
  for no reader's benefit.
- Any size-based tuning of the matching itself — a distance penalty for small
  images, a per-size threshold. The gate is binary because a binary gate is
  explicable in a report; a sliding one is not.

## Decisions

### D1 — Size is an eligibility gate, never a matching rule

**Chosen:** dimensions decide whether a candidate is *assessed*. They never
decide *what it matches* or *how close* it is.

This is the whole reconciliation with the existing requirement that "a candidate
image's filename, path, file format, and pixel dimensions MUST NOT determine
whether it matches a reference image", and with its scenario *Same logo at a
different size*. Both stay true: a 4000×4000 copy and a 200×200 copy of a
reference still match it, at the same distance, because trimming and luminance
hashing normalise scale. What changes is that a candidate below the minimum is
never presented to the strategy at all.

Stated as a gate rather than as an exception to content matching, the two
requirements compose instead of contradicting. It also fixes where the code goes
— in front of the matching seam, never inside `MatchStrategy` — so invariant 1's
ordering inside `signature_for()` is untouched and the replaceable-strategy
boundary keeps its meaning: a future strategy inherits the gate without knowing
it exists.

### D2 — Below the minimum in *either* dimension, measured on stored dimensions

**Chosen:** ineligible when `width < minimum or height < minimum`, against the
size the decoder reports.

Either-dimension, not both, and not area: a 600×1 horizontal rule and a 1×400
divider are exactly as unrecognisable as a 1×1, and an area test (`600 × 1 =
600 > 225`) admits both. Either-dimension is also the reading of "smaller than
15×15" that a person means when they say it.

**Rejected: measuring the trimmed content box instead.** It is the more
*correct* rule — a 300×300 PNG holding a 4×4 dot in the corner is as useless as
a 4×4 PNG — but it requires trimming first, which is most of the work the gate
exists to avoid, and it interacts badly with the blank check that already
handles the degenerate end of that case. Stored dimensions catch the population
that actually exists in these repositories at a fraction of the cost. Recorded
here so the next reader knows it was weighed rather than missed.

**Rejected: raising the minimum to something like 32.** Real 16×16 and 24×24
icons carry brand marks. 15 sits below every icon size in ordinary use and above
every spacer, which is the gap the default should fall in.

### D3 — The check sits in the loader, ahead of the blank check

**Chosen:** `images/loader.py::_load` takes the effective minimum and applies it
after decode (dimensions are not knowable before) and *before* `content_bbox`.

Ordering is the decision, not the placement. A 1×1 transparent spacer trips both
tests: it is undersized *and* it renders no content. Today it comes out as
`RENDERED_BLANK`, whose remediation tells the operator the file "can also be a
legitimately solid-colour swatch or spacer… confirm which, and replace it if it
should have held artwork." For a 1×1 GIF that is a demand to investigate
something already known. Undersized is the more specific and more useful truth,
so it wins, and the requirement says so rather than leaving it to fall out of
statement order in a function.

The knock-on is that `image-similarity-search`'s source-coverage requirement has
to be modified: it currently says an image that decodes but yields no content
SHALL be treated as a failed read, without qualification, and after this change
an undersized one is not. A large truncated image that renders nothing is
unaffected — it is still a failed read, still uncounted, still listed.

### D4 — A distinct exception, not a sixth `UnreadableCause`

**Chosen:** `ImageBelowMinimum`, raised by the loader, caught by
`scan/image_search.py`. Not an `ImageLoadError`, and no new `UnreadableCause`.

An undersized image is not an unreadable input. Every member of
`UnreadableCause` names something that went wrong and carries a remediation
saying how to make the input assessable; "it is 1×1" has no remediation, because
nothing is broken. Adding a sixth cause would put every spacer in the report's
unread section under a heading, which is the noise this change exists to remove
— and would quietly redefine a section the reporting spec describes as
*unassessed rather than clean*.

The cost is one more exception type on the load path, and the loader now signals
two different kinds of not-matched. That is the honest shape: the module's
docstring claim is that it is the only code that knows *why* an input was not
matched, and this is a second why.

### D5 — Exemptions are path globs, resolved by the caller

**Chosen:** `image_scope.always_examine`, a list of globs matched with
`walker.matches_any` — the same function, and therefore the same
basename-or-full-path semantics, as every other glob an operator writes in this
configuration. `scan_images` resolves each candidate to an effective minimum (0
when exempt) and passes it down; the loader knows sizes, not paths.

Seeded with `favicon*`, `apple-touch-icon*`, `*.ico`, `*.cur`.

At the default of 15 the seeded list changes nothing — a 16×16 favicon clears
15 on its own. That is not an argument against it. The exemption exists so the
minimum stays *tunable*: an operator who finds 20×20 sprite junk and raises the
minimum to 32 would otherwise drop every favicon in the estate in the same
edit, silently, and favicons are among the highest-value brand assets there are
— they are the brand in the browser tab of every deployed site. Better that the
protection is already in place and visible in the example configuration than
discovered as a miss two runs later.

For an embedded image the exemption is tested against its *containing* path,
which is all a data URI has. A tiny inlined icon in `index.html` is therefore
skipped rather than exempted. Accepted: the alternative is exempting every
undersized image inlined in any HTML file, which is most of them.

### D6 — Config shape: an `image_scope` block, not a scalar and not `scope`

**Chosen:**

```yaml
image_scope:
  min_dimension: 15
  always_examine:
    - "favicon*"
```

**Rejected: two top-level keys** (`min_image_dimension`, `favicon_globs`). Two
unrelated-looking top-level entries for one rule, and the second is named after
one use of a general mechanism.

**Rejected: folding it into the existing `scope` block.** `scope` decides which
*files are walked*; this decides which *decoded images are assessable*. They
read alike and act at different stages, and `scope.max_file_bytes` sitting next
to `image_scope.min_dimension` is a genuine confusability cost — but a
size-based rule that lives in the file-walking block and cannot be applied
during the walk is worse. The names are distinct and both are documented in the
example.

`min_dimension: 0` disables the gate, which is how a run reproduces
pre-change behaviour without a code change. It is validated as a non-negative
integer, rejecting booleans on the terms invariant 9 already sets — `true` would
otherwise be admitted as a minimum of 1.

### D7 — Skipped candidates are counted in the report, never listed

**Chosen:** `RepoResult.images_below_minimum`, rendered as one provenance line
beside *Images examined*, with the minimum in force on its own line and in the
JSON sidecar.

Invariant 6 says a thing that was not assessed must not be presented as assessed
and clean, so a silent skip is not available. A per-file listing is equally not
available: it reinstates the wall of spacers in a different section. A count
plus the rule that produced it is the smallest honest statement — the operator
can see that 2,140 images were ruled out at 15 pixels, and can re-run with
`min_dimension: 0` if that number looks wrong for the repository.

The count is per repository, computed where the images are, and travels in that
repository's own sidecar. It is not a run-level rollup, so invariant 14 is not
in play; it is also deliberately not in the executive summary, which counts
findings.

## Risks / Trade-offs

- **A genuinely tiny brand mark that is not a favicon is missed.** A 12×12
  toolbar icon in a legacy WebForms app is a real thing, and this change stops
  looking at it. → It was never reliably matched: at that size the hash is not
  measuring resemblance, so what is lost is a coin-flip, not a detection. The
  count in each report makes the loss visible per repository, `always_examine`
  exempts a known path, and `min_dimension: 0` restores the old behaviour for a
  targeted re-run. This is the trade-off the change *is*; it is accepted, not
  mitigated away.
- **15 is asserted, not measured.** It is chosen to sit between spacer sizes and
  the smallest real icon size, not fitted to this estate's data the way the
  similarity threshold was fitted to the validation set. → Cheap to revisit: it
  is one configuration value and every report records the one it ran under. A
  first real run's skipped counts are the evidence to settle it with.
- **Two runs either side of this change disagree on `images_examined` and on the
  unread section**, so the count alone no longer means the same thing over time.
  → Both the minimum and the skipped count are pinned in provenance, so the
  difference is readable rather than mysterious; findings are unaffected, and
  reports still pin `commit_sha` for finding-by-finding comparison.
- **1×1 spacers move out of "Decoded to nothing".** An operator who has learned
  to read that section will find it shorter. → That is the intended correction,
  and the new provenance lines say where the entries went.
- **`always_examine` reads like a scope include-glob and is not one.** It does
  not add files to the walk; a file outside `scope` is not reachable by it. →
  Named for what it does to an image already in scope, and documented in the
  example next to the minimum it exempts from.
