# Design — Classify unreadable image inputs

## Context

See `proposal.md` — Why. Constraints that shape the approach:

- **The decoders are third-party and lenient.** `svglib` logs to its own logger and returns `None`; `reportlab` raises from deep inside rendering; Pillow accepts truncated files by configuration. None of them know the repository-relative path, and none of them can be made to.
- **The scan already has the right shape.** `ScanIssue` exists, is recorded per file, and reaches both report forms. What is missing is the *cause*, not the plumbing.
- **This runs unattended over ~400 repositories.** Anything that writes to the console per bad file is unusable, and anything that raises is worse.

## Goals / Non-Goals

**Goals:**

- Give every unread input a cause an operator can act on.
- Stop a lenient decoder from turning an unread file into a clean one.
- Ensure nothing reaches the console except through the run log.

**Non-Goals:**

- Fetching Git LFS objects (declared out of scope in the proposal). Detection only.
- Repairing malformed images.
- Any change to matching, hashing, or thresholds.

## Decisions

### D1. Classification is a closed set, carried on the issue

`ScanIssue` gains a `cause` drawn from a fixed set rather than relying on its existing free-text `reason`.

Free text is what the code produces today, and it is why the report cannot group or count anything: `vector image could not be parsed: Document is empty` and `embedded image could not be decoded` are the same problem to a reader and different strings to a program. A closed set can be aggregated in the executive summary later, and can drive different remediation wording per cause.

The free-text `reason` stays alongside it, because the specific parser message is still the most useful thing when the cause is `malformed`.

*Alternative considered:* pattern-matching the parser's message at report time. Rejected — it couples the report to the wording of a third-party library, which will change without warning.

### D2. Detect emptiness on the bytes, before any decoder

An input is judged empty by inspecting its bytes: no bytes at all, or nothing left after removing whitespace, a byte-order mark, an XML declaration, and comments.

Doing this first is what makes the noise disappear at source — a parser that is never invoked cannot log. It is also the cheapest possible check, which matters when it runs against every image in every repository.

This deliberately treats a comment-only `<!-- artwork pending -->` stub as empty rather than malformed. It is a placeholder somebody committed on purpose, and reporting it as a defect trains an operator to ignore the section it appears in.

### D3. Contain third-party loggers by re-routing, not by silencing

The `svglib` and `reportlab` loggers get `propagate = False` and a handler that forwards their records into the run log at debug level, wrapped in a context that knows which file is being processed.

Silencing them outright (`logging.disable`, or removing handlers) would be simpler and is wrong: when a malformed file is genuinely puzzling, the parser's own message is the only real evidence, and discarding it leaves an operator with nothing. Re-routing keeps it, attaches the filename the library could not know, and keeps it out of the operator's face.

*Alternative considered:* capturing stderr around each parse. Rejected — it is process-global, so it would not survive the run being parallelised later, and it would also swallow output from anything else that happened to write during the same window.

### D4. A contentless result is a failed read, detected via the existing trim

After decode or rasterisation, an image with no content bounding box is classified as `rendered_blank` and recorded as unread.

This reuses `content_bbox`, which already returns `None` for a uniform image — the same machinery that decides where to trim decides whether there is anything to trim. No new notion of "blank" is introduced, so the two cannot drift apart.

**The trade-off is real:** a legitimately solid-colour image — a colour swatch, a spacer, a single-colour placeholder — is indistinguishable from a failed render by this test, and will now be reported as unread. That is defensible, because a uniform image has no layout and cannot meaningfully match a reference either way, so nothing is lost from matching. But it will add entries to the unread list in repositories full of swatches, and those entries are noise rather than defects. `rendered_blank` is a distinct cause precisely so that noise can be recognised and, if it proves heavy, filtered.

### D5. The loader decides the cause; callers only record it

`images/loader.py` raises a typed error carrying the classification. `scan/image_search.py` and `scan/embedded.py` catch it and record a `ScanIssue`; they do not inspect the file or infer anything.

The code that opened the file is the only code that knows why it failed. Spreading that inference to the callers would mean two places re-deriving it, and they would disagree the first time a new case appeared.

## Risks / Trade-offs

- **Counts shift between versions.** Blank renders move out of `images_examined` and into the unread list, so a repository previously reported clean may now show issues. → Unavoidable and intended; the provenance block already records the tool version, so two reports can be told apart. Worth stating plainly when the change lands rather than letting somebody discover it as a regression.
- **Solid-colour images become unread entries (D4).** → Accepted, with `rendered_blank` as its own cause so the noise is identifiable. Revisit if a validation run shows it dominating.
- **Re-routing loggers is global state.** Configuring another library's logger affects anything else in the process using it. → Confined to the two loggers actually implicated, and applied where logging is already configured, so it is done once in one place rather than scattered.
- **Empty-detection heuristics can misjudge an exotic file.** A file that is genuinely an image but begins with a very long comment could be misread. → The check only declares emptiness when *nothing* remains after stripping; anything else falls through to the decoder as it does today.

## Migration Plan

No data migration. Existing reports remain readable; new ones carry an extra field per unread input. There is no persisted state to upgrade — the checkpoint records only status and commit, and a re-run regenerates reports.

Rollback is reverting the change; nothing it writes is depended on by anything earlier.

## Open Questions

- Whether a legitimately solid-colour image deserves its own cause, separate from `rendered_blank` (D4). Deferrable: it is a refinement of one value in a closed set, and settling it needs the validation run to show whether swatches are common enough to matter. It changes no requirement, no approach, and no task.
