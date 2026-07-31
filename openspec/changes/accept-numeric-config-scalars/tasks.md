## 1. Failing tests first

Each test in this group must fail against the current code before any of group 2
is written. That is what makes it a test of the requirement rather than of the
implementation.

- [x] 1.1 Add `tests/test_config.py` cases for a bare numeral in `brand.legal`: a plain eight-digit number and one with a leading zero, both loaded from a YAML file, asserting validation succeeds and the `legal-strings` group carries the numeral as written
- [x] 1.2 Add the octal-trap case — `07654321` unquoted — asserting the resulting pattern is `07654321` and explicitly asserting it is **not** `2054353`. This is the test the whole change exists for; assert both directions
- [x] 1.3 Add cases for a numeral in the non-legal positions: `brand.names`, a user-defined search-group's `patterns`, a scope glob, `disable_search_groups`, and `targets[].repos`
- [x] 1.4 Add a case asserting a quoted value and an ordinary string value produce identical results to today, so the change is confined to what previously aborted
- [x] 1.5 Add rejection cases that must keep failing with a field-named `ConfigError`: a mapping, a nested list, an empty/null list entry, and a bare `No` (design D3, D5)
- [x] 1.6 Add typed-field regression cases: `similarity_threshold` and `scope.max_file_bytes` accept integers and reject non-integers **and booleans**; `include_archived`, `include_forks`, and `case_sensitive` accept real booleans and reject non-booleans. `similarity_threshold: true` must be rejected — design D3 identifies this as the specific way this change could weaken validation
- [x] 1.7 Add a case asserting a numeric value in `brand.colors` still fails `is_hex_colour` with its field named
- [x] 1.8 Add a case for a numeric reference-image label in the sidecar, asserting the label is the source text (design D7)
- [x] 1.9 Run the suite and record which of the above fail and with what message, confirming each targets a real gap

## 2. Loader implementation

- [ ] 2.1 Add `RawInt`/`RawFloat` subclasses and a `SafeLoader` subclass wrapping only the `int` and `float` constructors to attach `node.value` as `raw` (design D2, D3 — do **not** wrap `bool`)
- [ ] 2.2 Add a `scalar_text` helper returning `raw` when present and falling back to `str(value)` otherwise (design D4), with `None` and `bool` excluded so they stay rejections
- [ ] 2.3 Change `_string_list` to admit numeric scalars through `scalar_text`, leaving the existing field-named `ConfigError` for everything else
- [ ] 2.4 Point `load_config` at the new loader in place of `yaml.safe_load`
- [ ] 2.5 Cast `scope.max_file_bytes` with `int()` before storing it on `ScanScope`, so no raw-carrying value escapes into the rest of the system (design D6); confirm `similarity_threshold` already does this
- [ ] 2.6 Route `_load_sidecar_labels` in `references.py` through the same loader and `scalar_text` in place of `str(v)` (design D7)
- [ ] 2.7 Run the suite; every test from group 1 passes and the existing 203 continue to pass

## 3. Verification and documentation

- [ ] 3.1 Confirm by inspection that no `isinstance` check in `loader.py` was altered to accommodate this change — group 2 should have touched none of them (design D3)
- [ ] 3.2 Run an end-to-end scan against a synthetic fixture repository containing the literal text `07654321`, confirming the finding is reported — the requirement is about what a scan finds, not only what validation accepts
- [ ] 3.3 Update the example configuration and any config documentation to show a company number entered unquoted
- [ ] 3.4 Run `openspec validate accept-numeric-config-scalars --strict`
- [ ] 3.5 Tick each task above only once its verifying test passes, per the repository's working practice
