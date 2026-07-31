## MODIFIED Requirements

### Requirement: Image source coverage

Image matching SHALL cover common raster image formats, icon-container formats, vector images, and images recovered from base64-encoded data URIs. Vector images SHALL be rasterised before signature computation so that they pass through the same matching path as raster images.

An image that cannot be decoded or rasterised SHALL be skipped with the failure recorded, and MUST NOT end the scan of the containing repository.

Each skipped input SHALL be recorded with a classification of *why* it could not be read, because the remedies differ and an undifferentiated failure is not actionable. The classification SHALL distinguish at least: an empty input, an input that is not an image at all, a version-control pointer standing in for content that was never fetched, a malformed or truncated image, and an image that decoded but yielded no content.

An input that carries no content SHALL be recognised as empty without being submitted to a decoder, and SHALL be recorded as skipped-because-empty rather than as a failure. An input counts as empty when it has no bytes, or when it holds nothing but whitespace, a byte-order mark, a document declaration, or comments. A placeholder file is an ordinary thing to find in a repository and is not a defect to report as one.

An image that decodes or rasterises without error but yields no content SHALL be treated as a failed read and recorded as such. It MUST NOT be counted among the images successfully examined, because a lenient decoder that produces a blank result would otherwise let an unread file be reported as one that was read and found to contain nothing.

Diagnostic output produced by an underlying decoder or rasteriser MUST NOT reach the operator except through the system's own reporting, and every message concerning a file SHALL identify that file.

#### Scenario: Raster image candidate

- **WHEN** a repository contains a raster image matching a reference
- **THEN** it is reported as a match

#### Scenario: Icon-container candidate

- **WHEN** a repository contains an icon-container image whose content matches a reference
- **THEN** it is reported as a match

#### Scenario: Vector image candidate

- **WHEN** a repository contains a vector image whose rendered appearance matches a reference
- **THEN** it is reported as a match

#### Scenario: Malformed image file

- **WHEN** an image file cannot be decoded or rasterised
- **THEN** it is skipped and the failure is recorded
- **AND** the failure names the file and is classified as malformed
- **AND** the remaining images in that repository are still matched

#### Scenario: Empty image file

- **WHEN** an image file has no bytes
- **THEN** it is recorded as skipped because it is empty, not as a failure
- **AND** no decoder is invoked for it

#### Scenario: File containing only placeholder content

- **WHEN** a file with an image extension contains only whitespace, a byte-order mark, a document declaration, or comments
- **THEN** it is recorded as skipped because it is empty
- **AND** it is distinguished from a malformed image

#### Scenario: Version-control pointer in place of an image

- **WHEN** a file with an image extension contains a version-control pointer rather than image data
- **THEN** it is recorded as unread with that cause identified
- **AND** it is distinguished from a malformed image, because the remedy is to fetch the real content rather than to repair the file

#### Scenario: File that is not an image at all

- **WHEN** a file with an image extension contains unrelated content, such as an error page saved under that name
- **THEN** it is recorded as unread and classified as not an image

#### Scenario: Truncated image that decodes to nothing

- **WHEN** a truncated image is accepted by its decoder but yields no content
- **THEN** it is recorded as a failed read
- **AND** it is not counted among the images examined
- **AND** the repository is not reported as clean on the strength of it

#### Scenario: Decoder diagnostics during a run

- **WHEN** an underlying decoder or rasteriser emits its own diagnostic output for a file
- **THEN** that output does not reach the operator directly
- **AND** the corresponding record in the system's own reporting names the file it concerns
