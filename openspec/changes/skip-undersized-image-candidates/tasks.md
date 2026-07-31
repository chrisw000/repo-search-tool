## 1. Configuring the minimum

- [ ] 1.1 Add `DEFAULT_MIN_IMAGE_DIMENSION = 15` and an `ImageScope` dataclass
  (`min_dimension`, `always_examine`) to `config/model.py`, and the field on `Config`
  (D6)
- [ ] 1.2 Seed the favicon exemption globs (`favicon*`, `apple-touch-icon*`, `*.ico`,
  `*.cur`) in `config/defaults.py` beside the other seeded scope defaults (D5)
- [ ] 1.3 Parse the `image_scope` block in `config/loader.py`: `min_dimension` as a
  non-negative integer rejecting booleans on invariant 9's terms, `always_examine`
  through `_string_list`; absent block takes the seeded defaults
- [ ] 1.4 Test: an absent `image_scope` yields the documented default and the seeded
  exemptions — covers *Minimum not specified* and *Favicons exempt without
  customisation*
- [ ] 1.5 Test: `min_dimension` given a negative value, a non-integer and `true` each
  fail validation naming `image_scope.min_dimension` — covers *Minimum given a value
  that is not a non-negative integer*
- [ ] 1.6 Test: configured exemption patterns replace the seeded ones, and an empty
  list exempts nothing — covers *Exemptions replaced by configuration*

## 2. The eligibility gate

- [ ] 2.1 Add `ImageBelowMinimum` to `images/loader.py` — a distinct exception carrying
  the measured size, not an `ImageLoadError`, and with no `UnreadableCause` (D4)
- [ ] 2.2 Give `_load` the effective minimum and apply it after decode and **before**
  the `content_bbox` blank check; `open_image` and `open_image_bytes` both take it
  (D3)
- [ ] 2.3 Test: a candidate below the minimum in both dimensions raises
  `ImageBelowMinimum` and is never hashed — covers *Candidate below the minimum in
  both dimensions*
- [ ] 2.4 Test: a 600×1 rule is ineligible while a 15×200 image is not — covers
  *Candidate below the minimum in one dimension only* and *Candidate at the minimum*
  (D2)
- [ ] 2.5 Test: a 1×1 transparent spacer is reported as undersized, not as
  `RENDERED_BLANK` — covers *Undersized image that also yields no content* (D3)
- [ ] 2.6 Test: a large truncated image that renders nothing is still a failed read —
  covers *Truncated image that decodes to nothing* under its modified wording
- [ ] 2.7 Test: reference images are loaded whatever their size, so the gate never
  applies to the reference set (non-goal, asserted rather than assumed)

## 3. Applying the gate during a scan

- [ ] 3.1 In `scan/image_search.py`, resolve each candidate's effective minimum — 0
  where `walker.matches_any` matches `always_examine`, otherwise `min_dimension` —
  and pass it to the loader (D5)
- [ ] 3.2 Catch `ImageBelowMinimum` and count it in a new
  `ImageScanResult.images_below_minimum`; record no issue and no finding
- [ ] 3.3 Apply the same resolution to embedded images, testing the exemption against
  the containing path (D5)
- [ ] 3.4 Test: an undersized copy of a reference logo yields no finding and is counted
  as ruled out — covers *Undersized copy of a reference logo*
- [ ] 3.5 Test: a favicon below the minimum is assessed and counted among the images
  examined — covers *Exempted path below the minimum*
- [ ] 3.6 Test: an undersized image inlined as a data URI is ineligible — covers
  *Undersized image embedded as a data URI*
- [ ] 3.7 Test: `min_dimension: 0` assesses everything and rules nothing out — covers
  *Minimum disabled* and *Minimum disabled by configuration*
- [ ] 3.8 Test: a repository holding both undersized and normal images reports exactly
  the findings it did before this change for the normal ones — covers *Remaining
  images unaffected* and *Eligible candidates matched irrespective of their size*

## 4. Reporting what was ruled out

- [ ] 4.1 Add `Provenance.min_image_dimension` and `RepoResult.images_below_minimum` in
  `results.py`, both through `to_dict`/`from_dict` so a resumed run rebuilds them
  from the sidecar (D7)
- [ ] 4.2 Thread `config.image_scope` through `run.py` into the scan and into the
  provenance
- [ ] 4.3 Render the minimum and the ruled-out count in `report/markdown.py`'s
  provenance body, beside *Images examined*
- [ ] 4.4 Test: a report over a repository with undersized images states the count and
  the minimum, and lists none of them individually — covers *Repository containing
  undersized images*
- [ ] 4.5 Test: the Markdown and the JSON sidecar agree on both values — covers
  *Machine-readable form inspected*
- [ ] 4.6 Test: a resumed run rebuilding a result from its sidecar preserves both
  values
- [ ] 4.7 Confirm the executive summary and all three of its renderings need no edit
  (invariant 10) — undersized candidates produce no findings to aggregate

## 5. Documentation and validation

- [ ] 5.1 Add the documented `image_scope` block to `config.example.yaml`, in the image
  matching section beside `similarity_threshold`, explaining the minimum, the zero
  case, and why the favicon exemption exists
- [ ] 5.2 Confirm `test_the_shipped_example_configuration_is_valid` passes against the
  extended example
- [ ] 5.3 Run `openspec validate --specs --strict` and the full suite; record the new
  test count
- [ ] 5.4 On archive: sync the deltas into `openspec/specs/`, add the eligibility-gate
  invariant to `CLAUDE.md` (size gates assessment, never matching; the gate precedes
  the blank check), and update its test count and Outstanding section
