## Why

The seeded `font-references` group matches *every* font asset in a repository,
not every *brand* font asset. Its pattern is
`[\w\-./]+\.(?:woff2|woff|ttf|otf|eot)\b` — so `glyphicons-halflings-regular.woff2`
(Bootstrap) and `fa-regular-400.eot` (Font Awesome) match in every repository
that ships them, multiplied by the build-output directories that are
deliberately in scope. The group is seeded at medium severity, the same as
`font-names`, and the executive summary expands each group into the distinct
values it matched. The operator therefore reads a wall of third-party font
filenames ranked alongside a genuine `font-family: 'Novo Sans'` declaration.

The spec says the system detects references to **brand** fonts; the
implementation is brand-agnostic. That gap is the defect.

Tightening the pattern is not the fix. A brand font file frequently carries no
brand string in its name — `NS-Bold.woff2`, `webfont-regular.woff2` — so the
catch-all is deliberately miss-averse, and its own remediation text already
tells the reader to *check whether the hosted family is a brand font*. It is an
inventory bucket for manual triage that is currently presented as brand
evidence. The fix is to stop conflating the two, not to make the catch-all
precise.

## What Changes

- **Font asset references are attributed where they can be.** A font asset
  reference — a file path or an external font-service URL — whose text carries a
  configured brand font name is a brand finding, at medium severity, in the
  `font-references` group. Its excerpt names the font that tied it to the brand.
- **A font asset that cannot be attributed becomes an inventory item, not a
  brand finding.** It is recorded in a new seeded group,
  `unattributed-font-assets`, at low severity, whose description and remediation
  say plainly that this is a font asset the scan found rather than a brand match,
  and that a human must decide whether the family is a brand font. Nothing is
  dropped: the same references are still reported, still with path, line and
  context.
- **Search-groups gain match-text exclusions.** A group may declare
  `exclude_matches`, a list of regular expressions that veto a match by the text
  that matched. Today a group's `exclude` filters *paths* only, so there is no
  way to say "not this string" without rewriting the group's patterns wholesale.
  This is available to every group, not only the font ones, and is validated
  like `patterns` — a bad expression fails configuration with the field named.
- **`unattributed-font-assets` is seeded with a vendor denylist** covering
  well-known third-party icon and font packages (Glyphicons, Font Awesome,
  Bootstrap Icons, Material Icons, Ionicons, Octicons, Feather, Simple Line
  Icons, Typicons, Elusive). It is also seeded to veto anything the
  brand-attributed group already caught, so one reference never appears as both
  a brand finding and an inventory item. Both are ordinary seeded config:
  clearing `exclude_matches` on the group in one line restores the full
  inventory.
- **Not breaking.** No configuration that is valid today becomes invalid. The
  visible change is that vendor font filenames move from medium to low severity
  and into a separate, honestly-named row — which does change how repositories
  rank in the executive summary, deliberately.

## Capabilities

### New Capabilities

None. This corrects and extends behaviour inside two existing capabilities.

### Modified Capabilities

- `text-pattern-search`: **Font name and font reference coverage** is modified.
  It currently requires a finding for any font asset referenced by a recognised
  extension, without reference to the brand. It must instead distinguish an
  attributed brand font reference from an unattributed font asset, and say what
  each is reported as — while still requiring that neither is dropped.
- `scan-configuration`: **Default search-groups seeded** is modified, because the
  seeded set grows from six groups to seven and the requirement enumerates them.
  A new requirement covering match-text exclusions on a search-group is added,
  alongside the existing scope-glob behaviour in **Named, extensible
  search-groups**.

## Impact

- `src/brandscan/config/model.py` — `SearchGroup` gains `exclude_matches` and the
  compiled form of it.
- `src/brandscan/config/defaults.py` — `font-references` narrows to
  brand-attributed references; the `unattributed-font-assets` group and the
  vendor denylist are seeded; the external font-service patterns widen to match
  the whole URL so that attribution and exclusion can both see the family name.
- `src/brandscan/config/loader.py` — parses, validates and compiles
  `exclude_matches` in the `search_groups` override mechanism.
- `src/brandscan/scan/text.py` — applies the veto in `scan_file`, against the
  matched text.
- **No reporting change.** The executive summary already keys rows by group name
  and expands each into the values that matched, so both renderings and the JSON
  sidecar pick this up with no renderer edit and no font-specific special case
  (invariant 10 untouched).
- Tests: `tests/test_config.py`, `tests/test_text_search.py`, and the summary
  tests that assert the seeded group set.
- Documentation: `CLAUDE.md` gains an invariant for the attribution split when
  this change is archived.
