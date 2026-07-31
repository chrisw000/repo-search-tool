## 1. Failing tests first

- [ ] 1.1 Add tests for the confidence ladder: a distance of 0 and of 2 band as very high, 3–5 as high, 6–8 as medium, 9–12 as low, 13+ as very low
- [ ] 1.2 Add a test that at the default threshold of 10 the very-low band is omitted, and that the low band is present carrying zero when no finding fell in it
- [ ] 1.3 Add a test that a raised threshold brings the very-low band back into the output
- [ ] 1.4 Add tests that the breakdown row for a search-group carries that group's configured severity, and that a reference-label row carries the severity image findings carry
- [ ] 1.5 Add tests that a case-insensitive group folds `OldBrand`/`OLDBRAND` into one matched value showing the more frequent spelling, and that a case-sensitive group keeps them apart
- [ ] 1.6 Add tests that matched values are ordered most-frequent first, capped, and that the number of omitted values is stated
- [ ] 1.7 Add tests that an excerpt containing `|` does not break the Markdown table and one containing `<script>` is escaped in the HTML
- [ ] 1.8 Add a test that the HTML summary references no external stylesheet, script, font, or image
- [ ] 1.9 Add a test that walks the summary model and asserts the Markdown and HTML carry the same totals, ranked repositories, and breakdown rows

## 2. Confidence bands

- [ ] 2.1 Add the band ladder beside `DEFAULT_SIMILARITY_THRESHOLD` in `config/model.py`, as an ordered set of named bands with inclusive distance bounds
- [ ] 2.2 Add the lookup from a distance to its band, and the filter that drops bands lying wholly above a given threshold
- [ ] 2.3 Verify 1.1–1.3 pass

## 3. The summary model

- [ ] 3.1 Define the computed model: totals, ranked repositories, match breakdown rows, severity distribution, not-scanned list, run errors, threshold, band definitions
- [ ] 3.2 Build the match breakdown row for a search-group: findings, repositories, severity from its findings, and its matched values folded per the group's `case_sensitive` flag, ordered by frequency with the displayed spelling being the most frequent
- [ ] 3.3 Build the match breakdown row for a reference label: findings, repositories, severity, and the per-band distribution over the reachable bands
- [ ] 3.4 Apply the display caps — 10 matched values for the rendered documents, 50 for the JSON — carrying the omitted count alongside
- [ ] 3.5 Change `write_summary` to take the `Config`, and thread the threshold and group case sensitivity through to the model
- [ ] 3.6 Verify 1.4–1.6 pass against the model

## 4. Markdown rendering

- [ ] 4.1 Re-point the existing Markdown renderer at the model so it computes no aggregate of its own
- [ ] 4.2 Render the expanded breakdown: severity column, matched values or confidence bands beneath each row, and the omitted-value count
- [ ] 4.3 State the configured similarity threshold and each band's distance range alongside the bands
- [ ] 4.4 Escape pipes in matched values and in any other cell carrying repository content
- [ ] 4.5 Verify the existing Markdown summary tests still pass and that 1.7's Markdown half passes

## 5. HTML rendering

- [ ] 5.1 Add `summary_html_file` to `OutputLayout`
- [ ] 5.2 Add the HTML renderer over the model, covering every section the Markdown carries
- [ ] 5.3 Add the inline stylesheet: readable tables, sticky headers, severity and confidence pills that carry their name in text as well as their colour
- [ ] 5.4 Add the inline sort script as an enhancement, with every row and number present in the markup without it
- [ ] 5.5 Escape all repository-derived content on the way in
- [ ] 5.6 Make per-repository links resolve from the summary's own location, as the Markdown's do
- [ ] 5.7 Verify 1.7's HTML half, 1.8, and 1.9 pass

## 6. JSON sidecar

- [ ] 6.1 Rebuild `summary_dict` from the model rather than from its own second pass
- [ ] 6.2 Carry severity, matched values (to the JSON cap), and band distributions into the sidecar
- [ ] 6.3 Add a test that the sidecar's breakdown agrees with the rendered documents

## 7. Wiring and end to end

- [ ] 7.1 Update `run.py` to pass the config and write the HTML alongside the other two, keeping the Markdown as the reported summary path
- [ ] 7.2 Extend the end-to-end test so a run over synthetic repositories emits all three files, with the HTML carrying the same totals as the Markdown
- [ ] 7.3 Run the full suite and confirm it passes

## 8. Documentation

- [ ] 8.1 Update `CLAUDE.md`: the new test count, the third summary artifact in the layout, and an invariant covering the model-behind-three-renderings rule and the escaping of repository-derived content
- [ ] 8.2 Run `openspec validate --changes enrich-executive-summary --strict`
- [ ] 8.3 Open the generated HTML in a browser against a real run and confirm the tables read well, the bands are distinguishable, and the drill-through links resolve
