# Tasks — Classify unreadable image inputs

## 1. Classification model

- [ ] 1.1 Closed set of causes: `empty`, `not_an_image`, `vcs_pointer`, `malformed`, `rendered_blank` — with a remediation sentence per cause
- [ ] 1.2 `ScanIssue` carries the cause alongside its existing free-text reason, and both survive the JSON round trip
- [ ] 1.3 Typed loader error carrying the cause, so the code that opened the file is the only code that decides why it failed (D5)

## 2. Empty-input detection

- [ ] 2.1 Byte-level emptiness check: no bytes, or nothing left after whitespace, byte-order mark, document declaration, and comments (D2)
- [ ] 2.2 Run it before any decoder is invoked, for raster and vector alike, so a parser that would log is never reached
- [ ] 2.3 Record an empty input as skipped-because-empty rather than as a failure — a committed placeholder is not a defect

## 3. Cause classification

- [ ] 3.1 Recognise a version-control pointer standing in for unfetched content, and classify it distinctly from a malformed file
- [ ] 3.2 Recognise a file whose content is not an image at all, such as an error page saved under an image extension
- [ ] 3.3 Classify a decoder or rasteriser failure as malformed, keeping the underlying message as the free-text reason
- [ ] 3.4 Apply the same classification to images recovered from base64 data URIs, not only to files on disk

## 4. Contentless renders

- [ ] 4.1 Treat an image with no content bounding box as `rendered_blank` and record it as unread (D4)
- [ ] 4.2 Exclude it from the count of images examined, so a lenient decoder cannot turn an unread file into a clean one
- [ ] 4.3 Confirm a truncated vector — currently rendered as a blank canvas and silently counted as examined — is now recorded as unread

## 5. Third-party logger containment

- [ ] 5.1 Re-route the vector library's loggers into the run log at debug level, with propagation disabled (D3)
- [ ] 5.2 Attach the file being processed to those records, so a message the library could not attribute names its file
- [ ] 5.3 Confirm no third-party output reaches the console during a scan over a repository full of unreadable inputs

## 6. Reporting

- [ ] 6.1 Per-repository report lists each unread input with its cause and what would be needed to assess it
- [ ] 6.2 Distinguish causes in the report rather than presenting every entry as the same kind of defect
- [ ] 6.3 JSON sidecar carries the same classification, with no unread input present in one form and absent from the other
- [ ] 6.4 A repository with findings-free content but unread inputs reads as clean on findings while still listing what was not assessed

## 7. Verification

- [ ] 7.1 Fixture covering every classified cause: zero-byte, whitespace-only, byte-order-mark-only, declaration-only, comment-only, version-control pointer, error page under an image extension, truncated vector, malformed raster
- [ ] 7.2 Assert the console stays silent and the run log carries every message, each naming its file
- [ ] 7.3 Assert a truncated vector no longer counts toward images examined and no longer leaves its repository looking clean
- [ ] 7.4 Assert matching behaviour is unchanged — the existing image-matching suite still passes untouched
