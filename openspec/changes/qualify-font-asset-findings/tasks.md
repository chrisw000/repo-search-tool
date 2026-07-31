## 1. Match-text exclusions on a search-group

- [ ] 1.1 Add `exclude_matches: list[str]` to `SearchGroup` (`config/model.py`) and a
  compiled accessor alongside `compiled_patterns()`, using the same
  `case_sensitive` flag so an exclusion behaves like the patterns it narrows (D4)
- [ ] 1.2 Test: a group's compiled exclusions honour `case_sensitive` in both settings
  — covers *Exclusion case sensitivity follows the group*
- [ ] 1.3 Parse `exclude_matches` in `_apply_group_overrides` (`config/loader.py`)
  through `_string_list`, so a numeric scalar is admitted on the terms invariant 9
  already sets
- [ ] 1.4 Extend `_validate_patterns_compile` to compile exclusions too, raising
  `ConfigError` naming `search_groups[<name>].exclude_matches` — covers *Invalid
  exclusion expression*
- [ ] 1.5 Confirm the existing "no patterns and no colors" rejection still fires for a
  group carrying only `exclude_matches` — covers *Group with exclusions but no
  patterns*
- [ ] 1.6 Test: `exclude_matches` on a user-defined group and on a seeded group behave
  identically — covers *Exclusions added to a seeded group*

## 2. Applying the veto during search

- [ ] 2.1 In `scan_file` (`scan/text.py`), test each match's text against the group's
  compiled exclusions and discard it on a hit, recording no finding and no excerpt
- [ ] 2.2 Change the pattern loop to **continue** past a vetoed match instead of
  `break`, so a later pattern in the same group can still match that line (D4)
- [ ] 2.3 Where a group declares exclusions, iterate matches with `finditer` and take
  the first surviving one; keep `search` where it declares none (D4) — covers *Two
  matches on one line, one excluded*
- [ ] 2.4 Test: a match whose text an exclusion matches produces no finding — covers
  *Match excluded by its text*
- [ ] 2.5 Test: exclusions on one group leave another group's finding on the same text
  intact — covers *Exclusions are group-local*
- [ ] 2.6 Confirm the full suite runtime has not moved materially from its ~55s
  baseline (D4's `finditer` branch)

## 3. Splitting the font asset groups

- [ ] 3.1 Widen `EXTERNAL_FONT_SERVICES` patterns from bare hosts to host-plus-URL-tail
  in `config/defaults.py`, so attribution and exclusion can both read the family
  name from the matched text (D3)
- [ ] 3.2 Narrow the seeded `font-references` group to brand-attributed references:
  asset-path patterns carrying the `flexible_name_pattern` expansion of
  `brand.fonts`, plus service URLs naming a brand font. Keep it at
  `Severity.MEDIUM`
- [ ] 3.3 Update the `font-references` description and remediation to say it reports a
  font asset tied to a configured brand font (British spelling)
- [ ] 3.4 Test: `novo-sans-regular.woff2`, `NovoSans-Regular.woff2` and
  `novo_sans.ttf` all attribute from one configured font — covers *Font file named
  after a brand font*
- [ ] 3.5 Test: a service link naming a configured brand font attributes to the brand —
  covers *External font service link naming a brand font*
- [ ] 3.6 Add the seeded `unattributed-font-assets` group at `Severity.LOW`, carrying
  the existing broad font-extension pattern and the broad service patterns, with a
  description and remediation stating the asset was found rather than matched
  against the brand and that a human must establish whether the family is a brand
  font (British spelling)
- [ ] 3.7 Test: a font asset carrying no configured brand font name lands in
  `unattributed-font-assets` at a lower severity than an attributed one, and is not
  recorded as a brand finding — covers *Font file carrying no brand font name*
- [ ] 3.8 Test: a service link naming no configured brand font is an unattributed
  finding — covers *External font service link naming no brand font*
- [ ] 3.9 Test: the pre-existing scenarios *Font declared in a stylesheet*, *Embedded
  font file referenced* and *Externally hosted font service referenced* still pass
  unchanged

## 4. Seeding the vendor denylist

- [ ] 4.1 Seed `unattributed-font-assets` with `exclude_matches` for Glyphicons, Font
  Awesome, Bootstrap Icons, Material Icons, Ionicons, Octicons, Feather, Simple
  Line Icons, Typicons and Elusive (D5)
- [ ] 4.2 Seed it also with the brand-attributed patterns, so a reference never
  surfaces as both a brand finding and an inventory item — covers the "reported
  once" clause of the modified requirement
- [ ] 4.3 Test: `glyphicons-halflings-regular.woff2` and `fa-regular-400.eot` produce
  no finding, while `fa-novo-sans-400.woff2` is still a brand finding — covers
  *Well-known third-party font package*
- [ ] 4.4 Test: overriding the group with `exclude_matches: []` reports the vendor
  assets again — covers *Seeded font-asset exclusions cleared*
- [ ] 4.5 Test: `disable_search_groups: [unattributed-font-assets]` silences the
  inventory while brand-attributed references are still reported — covers *Seeded
  font-asset group disabled*
- [ ] 4.6 Test: with `brand.fonts` empty, the attributed group is dropped by the
  existing empty-group rule and every font asset is reported as unattributed —
  covers *No brand fonts configured*

## 5. Seeded group set and reporting

- [ ] 5.1 Update any test asserting the seeded group set to expect seven groups —
  covers *Default groups present without customisation*
- [ ] 5.2 Confirm `report/summary_model.py` and all three renderings pick up the new
  group with no edit and no font-specific branch (invariant 10)
- [ ] 5.3 End-to-end test over a synthetic repository carrying a brand font file, a
  Bootstrap glyphicons file, a Font Awesome file and a Google Fonts link, asserting
  the per-repo report and the executive summary place each in the right row at the
  right severity

## 6. Documentation

- [ ] 6.1 Document `exclude_matches` wherever `search_groups` fields are documented for
  the operator, distinguishing it from `exclude` (path globs)
- [ ] 6.2 Run `openspec validate --specs --strict` and the full suite; record the new
  test count
- [ ] 6.3 On archive: sync the deltas into `openspec/specs/`, add the attribution-split
  invariant to `CLAUDE.md`, and update its test count and Outstanding section
