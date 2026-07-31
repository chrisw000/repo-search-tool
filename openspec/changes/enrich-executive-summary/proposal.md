## Why

The executive summary answers "how much is there" and "where is it worst", but
its findings-by-search-group table is currently the weakest part of it: it names
a group and counts findings, and stops. A reader cannot see how serious that
group was configured to be, cannot see what text actually matched, and — for
image matches — cannot tell an exact logo hit from a candidate that scraped in
just under the threshold. So the one document intended for the owner of the
rebrand pushes them straight into 400 per-repository reports to answer questions
the rollup already has the data for.

It is also Markdown-only. Markdown renders acceptably in an editor, but the
summary is a wide-table document read by people who are not going to open it in
one — and the report tree may be handed over as files. A rendered HTML view
costs nothing to emit and makes the tables genuinely readable.

## What Changes

- The findings-by-search-group and reference-label table gains the **configured
  severity** of each row: for a search-group, the `severity` set against it in
  configuration; for a reference label, the fixed high severity image matches
  carry.
- That table is **expanded to show the values that actually matched**. A text
  row breaks down into the distinct matched excerpts under that group, ordered by
  frequency and capped, so a reader sees that `legacy-brand` fired on
  `OldBrand`, `oldbrand.co.uk` and `Old Brand Ltd` rather than just "312".
- Image rows break down by **likeness confidence band** instead — very high /
  high / medium / low / very low, derived from the perceptual-hash distance —
  because for an image the meaningful sub-division is how close the match was,
  not what string it was. Bands are absolute in distance so they mean the same
  thing across runs, and bands lying wholly beyond the configured similarity
  threshold are omitted rather than printed as permanently-empty rows.
- A **self-contained `executive-summary.html`** is emitted alongside
  `executive-summary.md` and `executive-summary.json`, carrying the same
  sections and the same numbers, with the severity and confidence bands
  visually distinguished and no external asset or network dependency.
- The JSON sidecar carries the same additions, so the machine-readable rollup
  does not fall behind the human ones.

Not in scope: search-groups that produced no findings still do not appear in
the breakdown (the table remains a findings breakdown, not a coverage report),
and the per-repository report is unchanged.

## Capabilities

### New Capabilities

None. This enriches an existing rollup rather than adding a capability.

### Modified Capabilities

- `executive-summary`: the breakdown-by-match-type requirement gains configured
  severity and a matched-value / confidence-band expansion; a new requirement
  covers emitting the summary as HTML alongside the Markdown, with the two
  rendered from one model so they cannot disagree.

## Impact

- `src/brandscan/report/summary.py` — the breakdown aggregation gains severity,
  matched values and confidence bands; rendering splits so Markdown and HTML
  share one computed model.
- New `src/brandscan/report/html.py` (or equivalent) — the HTML renderer and its
  inline stylesheet.
- `src/brandscan/paths.py` — a `summary_html_file` in the output layout.
- `src/brandscan/run.py` — writes the third artifact and reports its path.
- `src/brandscan/config/model.py` — a confidence-band ladder lives beside the
  similarity threshold it is anchored to.
- `write_summary` needs the configured similarity threshold, which it is not
  currently given; its signature changes.
- `tests/test_reporting.py` — new scenario coverage.
- No new runtime dependency: the HTML is generated directly, not converted from
  Markdown.
