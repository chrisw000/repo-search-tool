## Context

See `proposal.md` — Why. What matters for the approach:

- `report/summary.py` currently computes its aggregates (`totals`, `ranked`,
  `by_match`, `by_severity`) and renders Markdown from them in one pass, and
  builds the JSON sidecar from a second, near-parallel pass (`summary_dict`).
  The two already duplicate the shaping of `by_match`. Adding a third rendering
  on that footing would triple it.
- `write_summary(results, run_errors, markdown_path, json_path)` is a pure
  function of the results. It has no access to the `Config`, and it now needs
  two things only configuration knows: the similarity threshold (which bands
  were reachable) and each search-group's `case_sensitive` flag (whether two
  spellings are one matched value).
- A `Finding` already carries everything else needed: `matched` (group name or
  reference label), `severity` (copied from the group at scan time, or the fixed
  `IMAGE_SEVERITY` for image matches), `excerpt` (the literal matched text, from
  `match.group(0)`, capped at 240 characters), and `distance`.
- The matched values reaching the summary are content from ~400 scanned
  repositories — arbitrary bytes that happen to have matched a regex. They are
  not trusted input for either output format.
- Image findings only exist at all when `distance <= similarity_threshold`
  (default 10, `DEFAULT_SIMILARITY_THRESHOLD`), which constrains any band ladder
  drawn over them.

## Goals / Non-Goals

**Goals:**

- One computed model behind all three renderings, so Markdown, HTML and JSON
  cannot drift apart as this document grows.
- A confidence ladder whose labels mean the same thing in every run.
- Output that survives being copied to a file share and opened offline.

**Non-Goals:**

- No templating engine, no Markdown-to-HTML converter, no CSS framework. The
  project has no runtime web dependency and this is not the change that
  introduces one.
- No coverage view of groups that found nothing. That is a real gap, but it is
  a different requirement about what was *searched for* and it needs the
  `Config`'s group list rather than the results.
- No change to the per-repository report, to matching, or to what a `Finding`
  carries.

## Decisions

### D1: One computed model, three renderers

Introduce an explicit summary model — the totals, the ranked repositories, the
match breakdown (each row carrying its severity plus either its matched values
or its confidence bands), the severity distribution, the not-scanned list — and
render Markdown, HTML and JSON from it. No renderer computes an aggregate of
its own, and no renderer derives its content from another renderer's output.

*Why:* the spec now requires that the Markdown and the HTML "report the same
totals, the same ranked repositories, and the same breakdown rows", and that
neither be a subset of the other. Two hand-written renderers over shared data
can be checked by a test that walks the model; two renderers each doing their
own aggregation can only be checked by comparing prose.

*Alternative — generate HTML by converting the Markdown:* rejected. It adds a
dependency, it makes the HTML structurally unable to carry anything the Markdown
does not (severity styling, band colouring), and it inverts the relationship —
the Markdown table layout would become the constraint on the HTML.

### D2: Confidence bands are absolute in distance, not relative to the threshold

The ladder, in perceptual-hash Hamming distance:

| Band | Distance |
| --- | --- |
| Very high | 0–2 |
| High | 3–5 |
| Medium | 6–8 |
| Low | 9–12 |
| Very low | 13+ |

*Why absolute:* a reader comparing this run's summary against last month's, or
one host's against the other's, must be able to take "very high" to mean the
same thing. Bands defined as fractions of the configured threshold — the obvious
alternative, and the one that guarantees every band is populated — make
"very high" mean ≤2 in a run at threshold 10 and ≤5 in a run at threshold 20,
which quietly changes the meaning of the word between two documents that look
identical.

*Why these boundaries rather than 5/10/15/20:* findings only exist at or below
the configured threshold, whose default is 10. A ladder starting its second band
at 5 and its third at 10 collapses to two live bands under that default, and
everything from "medium" down is dead. The ladder above spends its resolution
inside the range where findings actually occur: 0–2 is the recoloured-or-
identical logo, 3–5 is the same layout redrawn or rescaled, and 9+ is where the
operator's validation set put the marginal calls. It still extends past the
default so that an operator who loosens the threshold to catch more gets a
ladder that keeps discriminating rather than one that lumps everything new into
its last band.

The ladder lives beside `DEFAULT_SIMILARITY_THRESHOLD` in `config/model.py`,
because the two numbers are only meaningful against each other and splitting
them invites one to be tuned without the other.

### D3: Omit unreachable bands; keep reachable empty ones

A band whose whole range lies above the configured threshold is dropped from the
output. A band the threshold reaches into is shown even at zero.

*Why:* at the default threshold of 10, "very low" (13+) can never hold a
finding. Printing it as a permanent zero trains the reader to read zeros as
noise — and the zeros that matter here are the reachable ones. "Low: 0" at
threshold 10 says every image match was a solid one, which is a genuine finding
about the run. "Very low: 0" at threshold 10 says nothing at all.

This is why the spec requires the threshold to be printed with the bands: which
bands are absent is itself information, and it is unreadable without the number
that caused it.

### D4: Severity comes from the findings; configuration supplies only what findings cannot

A breakdown row's severity is read from the findings counted in it, not looked
up in configuration.

*Why:* the finding already carries the group's configured severity, copied at
scan time. Re-deriving it from configuration lets a row disagree with the
findings it is counting — and for a reference-label row there is no group to
look up, so a configuration lookup would need a special case for exactly the
rows the spec treats identically. Findings within a row are uniform in severity
by construction; if that ever ceases to be true, the model records the set and
the renderers show it rather than silently picking one.

Configuration is threaded in for the two things no finding carries: the
similarity threshold (D3) and each group's `case_sensitive` flag (D5).
`write_summary` accordingly takes the `Config`. It stays a pure function — same
results and config in, same document out.

### D5: Matched values fold by the group's own case sensitivity

Distinct matched values are counted under a key that is the excerpt casefolded
when the group is case-insensitive, and the excerpt verbatim when it is
case-sensitive. The spelling displayed is the most frequent one seen.

*Why:* a case-insensitive group is one whose author declared that case does not
distinguish a match, so `OldBrand`, `OLDBRAND` and `oldbrand` are one value and
splitting them into three rows both triples the table and understates the top
value's real weight. A case-sensitive group's author declared the opposite, and
folding there would destroy the distinction they configured. Displaying the most
frequent spelling rather than the folded key keeps the row showing something
that actually appears in a repository.

Values are capped at the 10 most frequent per row for Markdown and HTML, with
the remainder reported as a count, and at 50 in the JSON sidecar for anyone
scripting against it. A colour group expanding to several notations across 400
repositories can produce hundreds of distinct spellings; the table exists to
show a reader what the group is catching, and past the first handful it stops
doing that. Each displayed value is truncated for width (the underlying excerpt
is already capped at 240 characters, which is far wider than a table column).

### D6: Both formats escape matched values; neither trusts them

Matched values are content from scanned repositories. In HTML they are escaped
(`&`, `<`, `>`, `"`) before insertion; in Markdown table cells the pipe is
escaped, as `_not_scanned_section` already does for skip reasons.

*Why:* an excerpt is whatever matched a regex in an arbitrary repository —
`<script>` in a template, a pipe in a Markdown file, a backtick in a shell
script. Unescaped, the first corrupts the HTML summary and the second silently
breaks the Markdown table's column alignment for that row. This is not a
security boundary so much as a correctness one, but it fails in the direction
that makes the document wrong without making it look wrong.

### D7: Static HTML, with sorting as progressive enhancement

The HTML carries an inline `<style>` block and a short inline `<script>` that
makes table headers sortable. Nothing is fetched: no CDN, no font, no external
stylesheet, no image. Every number and row is present in the markup, so the
document is complete and correct with scripting disabled; the script only
reorders rows already there.

*Why inline rather than a companion `.css`:* the spec requires the summary to
survive being copied or shared, and a report tree that loses its stylesheet in
transit renders as unstyled soup. One file has no such failure mode.

*Why any script at all:* the ranked table can run to 200 rows. Re-sorting it by
findings count or by repository name is the first thing a reader tries, and
providing it costs about twenty lines. Making it an enhancement rather than a
requirement means the offline-rendering scenario still holds.

Severity and confidence bands are shown as a coloured pill **and** their name in
text. Colour alone would fail the spec's without-colour scenario, and this
document is printed and pasted into tickets.

### D8: The HTML is always emitted, with no flag

`executive-summary.html` is written on every run, beside the `.md` and `.json`,
via a `summary_html_file` property on `OutputLayout`. No CLI option turns it on
or off.

*Why:* it is a few kilobytes derived from data already in memory, and a flag
would create runs whose output directory is missing a file another reader
expects. `run.py` continues to report the Markdown path as the run's summary
path so existing output and log expectations do not shift.

## Risks / Trade-offs

- **The band boundaries are a judgment call, not a measurement.** The threshold
  itself was settled empirically against a validation set; these boundaries
  divide the space beneath it by argument. → They are named constants beside the
  threshold, so a later empirical pass can move them in one place, and the spec
  fixes only that bands are absolute and ordered — not what the numbers are.
- **Distinct-value cardinality.** A group whose patterns expand to colour
  notations can produce thousands of distinct excerpts across 400 repositories,
  all held in a counter at rollup time. → Bounded in practice: findings for the
  whole run are already resident in memory, and a counter over their excerpts is
  strictly smaller than the findings themselves. The cap applies to output only,
  so it does not help memory and is not claimed to.
- **Three renderings of one model is three places to forget a new section.** →
  The mitigation is the spec's "the two renderings agree" scenario, tested by
  walking the model rather than by eyeballing two documents.
- **`write_summary` gains a required `Config` parameter.** A breaking signature
  change to an internal function. → It has one caller in `run.py` and its tests;
  the alternative — an optional parameter defaulting to `None` — would make the
  threshold silently absent and the bands silently wrong, which is the failure
  mode invariant 6 exists to prevent.
- **Colour choice.** The palette must stay legible in a browser's dark mode and
  when printed. → Pills carry their text label regardless, so the worst case is
  ugly, not ambiguous.
