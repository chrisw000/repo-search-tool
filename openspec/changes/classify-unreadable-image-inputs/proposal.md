## Why

A file the scanner could not read is currently indistinguishable from a file that held nothing — and in one case, from a file that was read successfully.

Three problems, all confirmed by reproduction against the current build:

1. **Messages leak from a third-party parser and name no file.** `svglib` logs `Failed to load input file! (Document is empty, line 1, column 1)` straight to stderr, once per unparseable SVG, bypassing the structured run log. It never says *which* file. Over ~400 repositories that is hundreds of unattributable lines, and an operator cannot act on any of them.

2. **Every cause collapses into one message.** A zero-byte placeholder, a comment-only `artwork pending` stub, a Git LFS pointer left behind by a shallow clone, and a genuinely corrupt file all report `vector image could not be parsed`. Their remedies have nothing in common. The LFS case matters most: large brand assets are exactly what a repository puts in LFS, so a whole class of the highest-value targets can go unread while the report looks unremarkable.

3. **A truncated vector is not detected as a failure at all.** `svglib` parses `<svg …><rect` leniently and renders a blank white canvas. The scanner counts it in `images_examined`, records no issue, and reports the repository clean. This is a silent miss, and it contradicts the existing principle that a file which was never really read must never be presented as having nothing in it.

## What Changes

- Classify every unreadable image input by cause, rather than emitting one undifferentiated parse failure. At minimum: **empty**, **not an image**, **Git LFS pointer**, **malformed**, and **rendered blank**.
- Detect a genuinely empty input — zero bytes, or only whitespace, byte-order mark, XML declaration, or comments — before invoking any parser, and record it as *skipped because empty* rather than as a failure. A placeholder file is not a defect.
- Treat a render that produces no content as a failed read rather than a successful examination, so it can never be counted as an image that was examined and found clean.
- Contain third-party logger output so that nothing reaches the operator except through the structured run log, and every message about a file names that file.
- Surface the classification in the per-repository report, so the unreadable-files section tells a reader what to do about each entry rather than only that something went wrong.

Applies to raster decoding as well as vector rasterisation. **No change to matching behaviour** — nothing here alters which images match a reference.

## Capabilities

### New Capabilities

None. This tightens the failure handling of existing capabilities rather than introducing a new one.

### Modified Capabilities

- `image-similarity-search`: the *Image source coverage* requirement currently says an image that cannot be decoded or rasterised is skipped with the failure recorded. It gains the obligation to classify the cause, to recognise an empty input without parsing it, and to treat a contentless render as a failed read rather than a successful one.
- `per-repository-reporting`: the unreadable-file reporting gains the obligation to carry each file's classification, so the report distinguishes a placeholder from a corrupt asset from an unfetched LFS object.

## Impact

- **Affected code:** `images/loader.py` and `images/raster.py` (classification and the empty-input guard), `findings.py` (`ScanIssue` gains a cause), `scan/image_search.py` and `scan/embedded.py` (recording it), `report/markdown.py` and the JSON sidecar (surfacing it), `logging_setup.py` (containing third-party loggers).
- **Affected behaviour:** counts change. Images that were previously counted as examined but rendered blank move into the unreadable set, so `images_examined` may fall and a repository previously reported clean may become one with recorded issues. That is the point of the change, but it means figures are not comparable across the two versions.
- **Dependencies:** none added. The `svglib` and `reportlab` loggers are configured rather than replaced.
- **Out of scope:** fetching Git LFS objects. This change detects and reports a pointer file; acquiring the real object is a separate decision about clone cost across ~400 repositories.
