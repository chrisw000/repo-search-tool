# Tasks — Classify unreadable image inputs

## 1. Classification model

- [x] 1.1 Closed set of causes: `empty`, `not_an_image`, `vcs_pointer`, `malformed`, `rendered_blank` — with a remediation sentence per cause
- [x] 1.2 `ScanIssue` carries the cause alongside its existing free-text reason, and both survive the JSON round trip
- [x] 1.3 Typed loader error carrying the cause, so the code that opened the file is the only code that decides why it failed (D5)

## 2. Empty-input detection

- [x] 2.1 Byte-level emptiness check: no bytes, or nothing left after whitespace, byte-order mark, document declaration, and comments (D2)
- [x] 2.2 Run it before any decoder is invoked, for raster and vector alike, so a parser that would log is never reached
- [x] 2.3 Record an empty input as skipped-because-empty rather than as a failure — a committed placeholder is not a defect

## 3. Cause classification

- [x] 3.1 Recognise a version-control pointer standing in for unfetched content, and classify it distinctly from a malformed file
- [x] 3.2 Recognise a file whose content is not an image at all, such as an error page saved under an image extension
- [x] 3.3 Classify a decoder or rasteriser failure as malformed, keeping the underlying message as the free-text reason
- [x] 3.4 Apply the same classification to images recovered from base64 data URIs, not only to files on disk

## 4. Contentless renders

- [x] 4.1 Treat an image with no content bounding box as `rendered_blank` and record it as unread (D4)
- [x] 4.2 Exclude it from the count of images examined, so a lenient decoder cannot turn an unread file into a clean one
- [x] 4.3 Confirm a truncated vector — currently rendered as a blank canvas and silently counted as examined — is now recorded as unread

## 5. Third-party logger containment

- [x] 5.1 Re-route the vector library's loggers into the run log at debug level, with propagation disabled (D3)
- [x] 5.2 Attach the file being processed to those records, so a message the library could not attribute names its file
- [x] 5.3 Confirm no third-party output reaches the console during a scan over a repository full of unreadable inputs

## 6. Reporting

- [x] 6.1 Per-repository report lists each unread input with its cause and what would be needed to assess it
- [x] 6.2 Distinguish causes in the report rather than presenting every entry as the same kind of defect
- [x] 6.3 JSON sidecar carries the same classification, with no unread input present in one form and absent from the other
- [x] 6.4 A repository with findings-free content but unread inputs reads as clean on findings while still listing what was not assessed

## 7. Verification

- [x] 7.1 Fixture covering every classified cause: zero-byte, whitespace-only, byte-order-mark-only, declaration-only, comment-only, version-control pointer, error page under an image extension, truncated vector, malformed raster
- [x] 7.2 Assert the console stays silent and the run log carries every message, each naming its file
- [x] 7.3 Assert a truncated vector no longer counts toward images examined and no longer leaves its repository looking clean
- [x] 7.4 Assert matching behaviour is unchanged — the existing image-matching suite still passes untouched

## Notes

- **Relay threshold (5.1).** Library records are relayed at their own warning
  level and above, which is exactly what their last-resort handler would have
  shown an operator. Nothing previously visible is lost; relaying their debug
  chatter as well would bury the run log under one entry per ignored SVG node
  across ~400 repositories.
- **Run-logger level.** `configure_logging` now sets the logger to DEBUG and
  lets the handlers decide, because the pre-existing file handler was already
  configured for DEBUG but the logger's own INFO level dropped those records
  before it ever saw them. Console output is unchanged.
