## Context

See `proposal.md` — Why, for the defect. The constraints that shape the
approach:

- **Invariant 5 / invariant 6** (`CLAUDE.md`): build output stays in scope, and
  nothing that was read may be reported as clean when it was not. Anything that
  removes a finding has to justify itself against a confident miss.
- **Invariant 8**: search-groups are config, not code. A new class of match — or
  a new way to suppress one — must not require a code change to use.
- **Invariant 10**: one model behind Markdown, HTML and the JSON sidecar. No
  renderer may learn about fonts.
- `scan_file` (`scan/text.py:59`) records **at most one finding per group per
  line**, and takes the first pattern that matches. Both facts constrain how a
  veto has to work.
- `SearchGroup.exclude` (`scan/walker.py:82`) is *path* globs, evaluated once per
  file before any pattern runs. It cannot express "not this string".

## Goals / Non-Goals

**Goals:**

- A font asset reference that can be tied to the configured brand vocabulary
  reports differently — and ranks differently — from one that cannot.
- Suppressing a class of matched text is a configuration edit, for any group.
- No renderer, and no part of the summary model, learns that fonts are special.

**Non-Goals:**

- Identifying a brand font by its *contents*. Parsing the `name` table out of a
  `woff2` to read its family would attribute `NS-Bold.woff2` correctly, and is a
  substantially larger change with a new dependency. Out of scope; the
  unattributed group exists precisely because that gap is real and permanent
  under filename matching.
- Recording in the report which exclusions fired, or how many matches they
  suppressed. The configuration file is the record of what was suppressed.
  Adding a suppression count to reporting is invariant 14's problem in a new
  place — a second set of numbers computed elsewhere in the run.
- Changing `font-names`. Declarations (`font-family: 'Novo Sans'`) are already
  brand-attributed by construction; only the *asset* group was brand-agnostic.

## Decisions

### D1 — Two seeded groups, not one group that classifies each finding

**Chosen:** split the seeded `font-references` group into a brand-attributed
group (keeping the name `font-references`, medium) and a new
`unattributed-font-assets` group (low).

**Rejected:** keep one group and give `Finding` an attribution field, letting
severity vary per finding.

Per-finding classification loses on three counts. `Finding.severity` is taken
from `group.severity` (`scan/text.py:89`) and the summary model keys a row by
`finding.matched` — the group name — carrying one severity per row; a group
whose findings disagree about severity would force the summary to special-case
it, which is invariant 10. The classification rule would live in code, so an
operator could not retune what counts as attributed — invariant 8. And the split
gets the whole existing configuration surface for free: severity, scope,
description, remediation, and `disable_search_groups` all already work per group,
so "stop reporting the inventory entirely" is a one-line config edit rather than
a new flag.

The cost is that `scan-configuration`'s seeded-group requirement enumerates the
set, so it grows from six groups to seven. That is a spec edit, which is the
right place for it to show up.

### D2 — Attribution is "the matched text carries a configured brand font name"

One rule, applied to both embedded file references and external font-service
links. `fonts.googleapis.com/css?family=Novo+Sans` is a brand finding;
`?family=Roboto` is an inventory item. Anything narrower would need a second
rule for URLs, and a second rule is a second thing to get wrong.

The attributed patterns are the existing `flexible_name_pattern` expansion of
`brand.fonts` embedded in an asset-path pattern, so `novo-sans-regular.woff2`,
`NovoSans-Regular.woff2` and `novo_sans.ttf` all attribute from one configured
value — the same expansion `font-names` already uses, so the two font groups
cannot drift in what they consider the brand's font.

Consequence, specified rather than incidental: with no `brand.fonts` configured,
nothing can be attributed, the attributed group has no patterns and is dropped by
the existing empty-group rule (`config/loader.py:315`), and every font asset is
an inventory item. That is the correct degenerate case — not a silent loss.

### D3 — External font-service patterns widen to the whole URL

Today they match the host alone (`re.escape("fonts.googleapis.com")`). Both
attribution (D2) and exclusion (D4) read the *matched text*, so a pattern that
stops at the host makes the family name invisible to both, and every Google
Fonts link would be unattributable regardless of what it requests. The patterns
become host-plus-URL-tail. This is a pattern-breadth fix, not a mechanism one —
worth stating because the temptation under D4 is to widen the *veto* to the
whole line instead, which D4 rejects.

### D4 — `exclude_matches` vetoes per match, against the matched text

Named `exclude_matches`, not `exclude_patterns`, to sit unambiguously beside the
existing `exclude` (path globs) and to say what it acts on: a match. Compiled
with the group's own `case_sensitive` flag, so an exclusion behaves like the
patterns it narrows.

Vetoing against the **whole line** was considered and rejected: a line carrying
both a vendor font link and a brand one would be suppressed entirely, which is a
confident miss (invariant 6). The cost of vetoing against matched text is that a
pattern which matches too little cannot be excluded usefully — that is D3, and it
is a pattern-design responsibility from here on.

Two implementation consequences follow, and both are load-bearing:

- The pattern loop in `scan_file` must **continue** past a vetoed match rather
  than `break`, so a later pattern in the same group can still match the line.
- A single pattern can match a line more than once, and `re.search` only ever
  sees the first. If the first occurrence is vetoed and a second is not, `search`
  would lose it. Where a group has exclusions, iterate matches (`finditer`) and
  take the first surviving one; where it has none, keep `search`. The branch is
  worth it: this loop runs over every line of every file of ~400 repositories.

### D5 — The vendor denylist is seeded, and it is safe against invariant 5

`unattributed-font-assets` is seeded with `exclude_matches` covering Glyphicons,
Font Awesome, Bootstrap Icons, Material Icons, Ionicons, Octicons, Feather,
Simple Line Icons, Typicons and Elusive — plus the brand-attributed patterns
themselves, so one reference never surfaces as both a brand finding and an
inventory item.

Invariant 5 says a confident miss is not cheap, and this list does remove
findings. Three things make it defensible, in descending order of weight:

1. **The vetoed pattern never proved anything about content.** It only ever
   proved that a font file exists at a path. A vendor font file that someone
   forked and injected a brand glyph into is not detected by the filename
   pattern either way — that is image search's job, and image search is
   untouched. So the denylist suppresses no evidence the pattern was actually
   providing.
2. **It only ever fires in the low-severity inventory group.** A brand-named
   asset is attributed by D2 before the inventory group is consulted, and the
   denylist is not applied to the attributed group at all. A file called
   `fa-novo-sans-400.woff2` is still a brand finding.
3. **It is seeded config, not a built-in.** `exclude_matches: []` on the group
   restores the full inventory in one line, and `disable_search_groups` removes
   the group altogether. Invariant 8 holds: the list is data.

The honest cost remains: it is a maintenance list of third-party product names
living in `config/defaults.py`, it will go stale as icon packages come and go,
and it encodes an assumption — that these families are never the old brand's —
that is true for this estate and asserted rather than proven for any other.
Recorded here so the next reader does not have to rediscover it.

## Risks / Trade-offs

- **A rebranded asset named after a vendor package is hidden.** → It was never
  visible to a filename pattern in any useful sense (D5.1); image search covers
  the content. Clearing `exclude_matches` restores the inventory for a targeted
  re-run.
- **Repository ranking in the executive summary shifts.** Vendor font noise moves
  from medium to low, so repositories previously ranked up by it fall. This is
  the intended correction, not a side effect — but a run taken before this change
  and one taken after are not comparable on rank alone. Reports pin
  `commit_sha`, so the comparison is still possible finding-by-finding.
- **`finditer` in the scan hot loop.** → Only on groups that declare exclusions;
  groups without them keep `search`. Worth confirming the full-suite runtime does
  not move materially.
- **`exclude` and `exclude_matches` are confusable in config.** → Distinct names,
  distinct validation errors, and both documented on the group; the field-named
  error already tells an operator which one they got wrong.
- **`exclude_matches` is a general mechanism introduced for one caller.** → It is
  the invariant-8-shaped fix: the alternative is a font-specific denylist in
  code, which is the thing invariant 8 exists to prevent. Its second caller will
  be whichever group the operator finds noisy next.
