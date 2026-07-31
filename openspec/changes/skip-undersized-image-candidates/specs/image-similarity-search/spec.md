## MODIFIED Requirements

### Requirement: Filename-independent content matching

Image matching SHALL be determined by image content. A candidate image's
filename, path, file format, and pixel dimensions MUST NOT determine which
reference image it matches, nor the measured distance to that reference.

This governs *how a candidate is matched*, not *whether it is assessed*. A
candidate's dimensions and path MAY determine its eligibility for assessment, as
required by **Minimum candidate image size**; a candidate admitted for
assessment SHALL then be matched on content alone.

#### Scenario: Same logo under an unrelated filename

- **WHEN** a repository contains a copy of a reference logo saved under a filename bearing no relation to the brand
- **THEN** it is reported as a match

#### Scenario: Same logo in a different file format

- **WHEN** a repository contains a copy of a reference logo saved in a different image format from the reference
- **THEN** it is reported as a match

#### Scenario: Same logo at a different size

- **WHEN** a repository contains a copy of a reference logo at different pixel dimensions from the reference
- **THEN** it is reported as a match

#### Scenario: Eligible candidates matched irrespective of their size

- **WHEN** two eligible candidates contain the same logo at substantially different pixel dimensions
- **THEN** both are reported as matches against the same reference
- **AND** neither is preferred over the other on the strength of its size

### Requirement: Image source coverage

Image matching SHALL cover common raster image formats, icon-container formats, vector images, and images recovered from base64-encoded data URIs. Vector images SHALL be rasterised before signature computation so that they pass through the same matching path as raster images.

An image that cannot be decoded or rasterised SHALL be skipped with the failure recorded, and MUST NOT end the scan of the containing repository.

Each skipped input SHALL be recorded with a classification of *why* it could not be read, because the remedies differ and an undifferentiated failure is not actionable. The classification SHALL distinguish at least: an empty input, an input that is not an image at all, a version-control pointer standing in for content that was never fetched, a malformed or truncated image, and an image that decoded but yielded no content.

An input that carries no content SHALL be recognised as empty without being submitted to a decoder, and SHALL be recorded as skipped-because-empty rather than as a failure. An input counts as empty when it has no bytes, or when it holds nothing but whitespace, a byte-order mark, a document declaration, or comments. A placeholder file is an ordinary thing to find in a repository and is not a defect to report as one.

An image that decodes or rasterises without error but yields no content SHALL be treated as a failed read and recorded as such. It MUST NOT be counted among the images successfully examined, because a lenient decoder that produces a blank result would otherwise let an unread file be reported as one that was read and found to contain nothing.

An image that is ineligible under **Minimum candidate image size** SHALL be recorded as undersized rather than as a failed read, whether or not it also yields no content. The size rule takes precedence, because it is the more specific account of the same input: a one-pixel spacer is not a damaged image and no remedy would make it assessable. An image large enough to be eligible that yields no content SHALL continue to be recorded as a failed read.

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

- **WHEN** a truncated image large enough to be eligible is accepted by its decoder but yields no content
- **THEN** it is recorded as a failed read
- **AND** it is not counted among the images examined
- **AND** the repository is not reported as clean on the strength of it

#### Scenario: Undersized image that also yields no content

- **WHEN** an image below the minimum candidate size decodes without error and yields no content, such as a single-pixel transparent spacer
- **THEN** it is recorded as undersized
- **AND** it is not recorded as a failed read, and not listed among the inputs that could not be read

#### Scenario: Decoder diagnostics during a run

- **WHEN** an underlying decoder or rasteriser emits its own diagnostic output for a file
- **THEN** that output does not reach the operator directly
- **AND** the corresponding record in the system's own reporting names the file it concerns

## ADDED Requirements

### Requirement: Minimum candidate image size

A candidate image SHALL be assessed only when it is large enough to carry a
recognisable layout. A candidate whose width or height is below the configured
minimum SHALL be ineligible: it MUST NOT be hashed, matched, or reported as a
finding. Below that size a similarity distance no longer measures resemblance,
so assessing such a candidate produces a false finding or an unactionable
record rather than evidence.

The rule SHALL be applied to the image's own stored dimensions, and SHALL apply
to every candidate irrespective of how it was obtained, including an image
recovered from a base64 data URI. It SHALL NOT be applied to reference images,
which are a deliberate, labelled choice by the operator rather than incidental
content found in a repository.

A candidate whose path matches a configured exemption SHALL be assessed whatever
its size, so that a class of legitimately small brand asset — a favicon above
all — survives any minimum an operator chooses. For an image recovered from a
data URI the exemption SHALL be tested against the path of the file containing
it.

An ineligible candidate MUST NOT be counted among the images examined, because
an image that was ruled out was not assessed and found clean. It SHALL be
recorded as a count per repository rather than enumerated file by file: a
repository can hold thousands of such images, and listing them reinstates in one
section the noise the rule removes from another.

The minimum SHALL be recorded in each repository's report alongside the number
of candidates it ruled out, so that a report states what it did not assess
rather than leaving it to be inferred.

#### Scenario: Candidate below the minimum in both dimensions

- **WHEN** a repository contains an image smaller than the configured minimum in both dimensions, such as a single-pixel spacer
- **THEN** it is not matched against any reference
- **AND** no finding is recorded for it
- **AND** it is not counted among the images examined

#### Scenario: Candidate below the minimum in one dimension only

- **WHEN** a repository contains an image whose width is comfortably above the minimum but whose height is below it, such as a one-pixel-high rule
- **THEN** it is ineligible on the same terms as one below the minimum in both dimensions

#### Scenario: Candidate at the minimum

- **WHEN** a repository contains an image whose smaller dimension equals the configured minimum
- **THEN** it is eligible and is matched normally

#### Scenario: Undersized copy of a reference logo

- **WHEN** a repository contains a copy of a reference logo scaled below the configured minimum
- **THEN** no image finding is reported for it
- **AND** the report records it among the candidates ruled out by the minimum

#### Scenario: Exempted path below the minimum

- **WHEN** a repository contains an image below the configured minimum whose path matches a configured exemption, such as a favicon
- **THEN** it is assessed and matched normally
- **AND** it is counted among the images examined

#### Scenario: Undersized image embedded as a data URI

- **WHEN** a file contains a base64 data URI carrying an image below the configured minimum
- **THEN** it is ineligible on the same terms as an image read from a file

#### Scenario: Minimum disabled

- **WHEN** the configured minimum is zero
- **THEN** every candidate is assessed whatever its size
- **AND** no candidate is recorded as ruled out by the minimum

#### Scenario: Remaining images unaffected

- **WHEN** a repository contains both undersized images and images above the minimum
- **THEN** the images above the minimum are matched normally
- **AND** the repository's findings are unchanged by the presence of the undersized ones
