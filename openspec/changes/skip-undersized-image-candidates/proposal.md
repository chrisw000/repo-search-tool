## Why

Image matching hashes every image it can decode, whatever its size. Across ~400
repositories — with build output deliberately in scope (invariant 5) — that
means every 1×1 tracking pixel, every 8×8 bullet, every 600×1 rule and every
spacer GIF a decade of front-end work left behind is trimmed, hashed and
compared against the reference set.

Nothing useful comes back. A perceptual hash is a coarse description of a
layout, and an image a dozen pixels across has no layout to describe: after the
trim it is a handful of luminance samples, which collapse onto whatever
reference happens to be nearest. Below roughly a dozen pixels the distance to a
reference stops measuring resemblance at all. So the tiny images produce two
outcomes, both wrong — a false image finding at high severity, or, more often, a
`RENDERED_BLANK` issue in the report's unread section, where a 1×1 transparent
spacer is presented to the operator as an asset that "decoded but yielded no
content" and told to confirm whether it should have held artwork. It should not.
It is a spacer.

They also cost the run. A repository with a checked-in sprite pipeline can carry
thousands of them, each decoded, trimmed and hashed to reach a foregone
conclusion.

The one class of legitimately tiny image that *does* carry brand is the favicon.
It must survive the cut — at the default minimum it would anyway, but the
operator has to be able to raise the minimum without silently dropping the one
brand asset in the estate that is 16 pixels across on purpose.

## What Changes

- **A candidate image below a minimum pixel size is not matched.** The rule is
  measured on the image's own stored dimensions: a candidate whose width or
  height is below the minimum is ineligible. `15` is the documented default, so
  the common junk sizes (1×1, 8×8, 10×10, 600×1) go and the smallest icon sizes
  in real use (16×16) stay.
- **The minimum is configurable**, in a new `image_scope` block alongside
  `similarity_threshold`. `min_dimension: 0` restores today's behaviour of
  matching every image whatever its size. The value in force is recorded in
  every report's provenance block, exactly as the similarity threshold already
  is.
- **Paths can be exempted from the minimum**, by glob, in
  `image_scope.always_examine`. It is seeded with the favicon family
  (`favicon*`, `apple-touch-icon*`, `*.ico`, `*.cur`), and it is ordinary
  configuration: an operator who raises `min_dimension` to 32 keeps their 16×16
  favicons without a code change, and one who wants no exemptions at all clears
  the list.
- **A skipped image is counted, not listed.** Each repository's report records
  how many candidates were skipped as undersized and what minimum was in force.
  It is not counted among the images examined and it is not filed as an unread
  input — it was read perfectly well, it was ruled out. Reporting a count rather
  than a row per file is the whole point: a per-file listing of 2,000 spacers is
  the noise this change removes, wearing a different hat.
- **The size check precedes the blank check**, so a 1×1 transparent spacer is
  now recorded as undersized rather than as an image that decoded to nothing.
  This is a deliberate reclassification of a case the current wording covers,
  and it is why `image-similarity-search`'s source-coverage requirement is
  modified rather than merely extended.
- **Not breaking for configuration.** Every configuration valid today remains
  valid and gains the seeded default. It *is* a behaviour change for a run: a
  scan taken before this change and one taken after will disagree on
  `images_examined` and on the unread section, which is why both the minimum and
  the skipped count are pinned in provenance.

## Capabilities

### New Capabilities

None. This narrows what one existing capability assesses and adds one
configuration surface to another.

### Modified Capabilities

- `image-similarity-search`: **Filename-independent content matching** is
  modified. It currently forbids pixel dimensions from determining whether a
  candidate matches, which is exactly what this change introduces — but for a
  different question. The requirement must separate *which reference a candidate
  matches* (content alone, unchanged: a logo at 4000×4000 and the same logo at
  200×200 both match) from *whether a candidate is assessed at all* (an
  eligibility gate, which size may govern). Left unqualified, the requirement
  and the new one contradict each other. **Image source coverage** is modified
  for the precedence rule described above. A new requirement, **Minimum
  candidate image size**, is added covering the rule, the exemption, and the
  accounting.
- `scan-configuration`: a new requirement is added covering the configurable
  minimum, its documented default, its exemption list, and the validation of
  both.
- `per-repository-reporting`: **Provenance block** is modified to record the
  minimum in force and the number of candidates it skipped, so that a report
  states what it did not look at rather than leaving it to be inferred from a
  count that quietly shrank.

## Impact

- `src/brandscan/config/model.py` — a new `ImageScope` dataclass
  (`min_dimension`, `always_examine`) and `DEFAULT_MIN_IMAGE_DIMENSION = 15`;
  `Config` gains the field.
- `src/brandscan/config/loader.py` — parses and validates the `image_scope`
  block: `min_dimension` a non-negative integer rejecting booleans on invariant
  9's terms, `always_examine` through `_string_list`.
- `src/brandscan/config/defaults.py` — the seeded favicon exemption globs.
- `src/brandscan/images/loader.py` — `_load` gains the minimum, applied after
  decode and *before* the `content_bbox` blank check; a distinct
  `ImageBelowMinimum` exception, not an `ImageLoadError`, because it is not an
  unreadable input and must not acquire an `UnreadableCause`.
- `src/brandscan/scan/image_search.py` — resolves the effective minimum per
  candidate (0 where `always_examine` matches, reusing `walker.matches_any` so
  the glob semantics are the ones already documented for config globs), catches
  `ImageBelowMinimum`, and counts it in a new
  `ImageScanResult.images_below_minimum`.
- `src/brandscan/results.py` — `RepoResult.images_below_minimum` and
  `Provenance.min_image_dimension`, both into `to_dict`/`from_dict` so a resumed
  run rebuilds them from the sidecar.
- `src/brandscan/run.py` — threads `config.image_scope` into the scan and the
  provenance.
- `src/brandscan/report/markdown.py` — two provenance lines.
- **No executive-summary change.** The summary aggregates findings, and
  undersized candidates produce none. Invariant 10 is untouched: no renderer
  learns about image sizes.
- `config.example.yaml` — the `image_scope` block, documented.
- Tests: `tests/test_images.py`, `tests/test_unreadable_images.py`,
  `tests/test_config.py`, `tests/test_reporting.py`, `tests/test_end_to_end.py`.
- Documentation: `CLAUDE.md` gains an invariant for the eligibility-gate split
  when this change is archived.
