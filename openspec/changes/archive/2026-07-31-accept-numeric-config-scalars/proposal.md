## Why

A UK company number is a bare eight-digit numeral. Putting one in `brand.legal` —
the natural way to search an estate for a legacy legal entity — makes YAML resolve
it to an integer, and configuration validation aborts with
`brand.legal[0]: must be a string`. The operator's only recourse is to know they
must quote it, which nothing in the error tells them.

The reason this cannot be fixed by coercing with `str()` is the second half of the
problem. PyYAML implements YAML 1.1, where a leading-zero numeral made only of
octal digits is octal: `07654321` is parsed as the integer `2054353`. Coercing
that would produce the pattern `"2054353"`, and a scan over ~400 repositories would
report *clean* for every repository that actually carries the company number —
a confident miss, which is precisely what invariant 6 (clean is not the same as
skipped or failed) exists to prevent. The value the operator typed must survive.

## What Changes

- String-list positions in the configuration accept YAML numeric scalars, and take
  the scalar's **source text** rather than the parsed value's repr. `07654321`
  becomes the string `"07654321"`, not `"2054353"`.
- The rule applies to every string-list position, not just legal strings:
  `brand.names`, `brand.fonts`, `brand.domains`, `brand.legal`, `brand.colors`,
  `search_groups[].patterns`, `.include`, `.exclude`, `.colors`,
  `disable_search_groups`, `scope.exclude_dirs`, `.exclude_globs`,
  `.include_globs`, `targets[].repos`, and `reference_images.labels`. Seeded
  groups are ordinary groups (invariant 8), so a coercion rule that only
  `legal-strings` enjoyed would make it privileged.
- A value that is not a numeric scalar is still rejected with the existing
  field-named error: mappings, nested lists, empty entries, and YAML's boolean
  words. design.md D3 and D5 record why each stays out.
- Genuinely typed fields are untouched. `similarity_threshold` and
  `scope.max_file_bytes` remain integers; `include_archived`, `include_forks`, and
  `case_sensitive` remain booleans, each keeping its current validation.
- Not breaking: every configuration that loads today loads unchanged and produces
  the same patterns. This only admits inputs that previously aborted the run.

## Capabilities

### New Capabilities

None. This extends an existing capability rather than introducing one.

### Modified Capabilities

- `scan-configuration`: the validation contract gains a requirement governing how
  a scalar written in a string-list position is admitted and converted — source
  text, not parsed value — and states which fields remain strictly typed. The
  existing "Single declarative configuration source" requirement is unchanged in
  wording but is now qualified by it, so the delta adds a requirement rather than
  modifying one.

## Impact

- `src/brandscan/config/loader.py` — `_string_list` gains scalar coercion;
  `load_config` reads YAML through a loader that preserves scalar source text.
  `_parse_targets`, `_parse_group_overrides`, and `_parse_scope` inherit the
  behaviour through `_string_list` without individual changes.
- `validate_config` is also called directly with plain Python dicts, by the test
  suite and by the CLI paths that supply repositories from `--repo` and
  `--external-root`. Plain integers arriving without source text need a defined
  fallback; design.md settles it.
- `src/brandscan/config/references.py` — `_load_sidecar_labels` coerces labels
  with `str(v)`, which carries the identical defect. It reads through the same
  loader and helper rather than leaving one instance of the bug behind.
- No change to acquisition, scanning, reporting, or the run log. No new
  dependency — PyYAML is already the loader.
- `tests/test_config.py` — new scenario tests, including the octal-trap case,
  each failing before the change.
