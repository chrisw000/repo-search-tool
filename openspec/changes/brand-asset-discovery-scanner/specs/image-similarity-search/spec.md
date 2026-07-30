## Purpose

Finds old-brand imagery by what it looks like rather than what it is called, so that logos survive renaming, reformatting, resizing, recolouring, and padding and are still detected. This is the capability that makes the scan trustworthy, since filenames across the estate are unreliable.

## ADDED Requirements

### Requirement: Filename-independent content matching

Image matching SHALL be determined by image content. A candidate image's filename, path, file format, and pixel dimensions MUST NOT determine whether it matches a reference image.

#### Scenario: Same logo under an unrelated filename

- **WHEN** a repository contains a copy of a reference logo saved under a filename bearing no relation to the brand
- **THEN** it is reported as a match

#### Scenario: Same logo in a different file format

- **WHEN** a repository contains a copy of a reference logo saved in a different image format from the reference
- **THEN** it is reported as a match

#### Scenario: Same logo at a different size

- **WHEN** a repository contains a copy of a reference logo at different pixel dimensions from the reference
- **THEN** it is reported as a match

### Requirement: Content bounding-box trimming before hashing

The system SHALL trim both reference and candidate images to their content bounding box before computing a similarity signature, so that surrounding padding does not shift image features and defeat matching.

Trimming SHALL handle transparent padding and uniform solid-colour padding, and SHALL tolerate faint or anti-aliased edges so that near-uniform borders do not prevent the trim.

Trimming SHALL occur before any colour-mode conversion of the image. Converting an image's colour mode before trimming can introduce a full-frame channel that makes the image appear untrimmable, so the ordering is required, not incidental.

#### Scenario: Logo surrounded by transparent padding

- **WHEN** a candidate contains a reference logo surrounded by transparent padding
- **THEN** it is reported as a match

#### Scenario: Logo surrounded by solid-colour padding

- **WHEN** a candidate contains a reference logo surrounded by uniform solid-colour padding
- **THEN** it is reported as a match

#### Scenario: Same logo occupying different proportions of its frame

- **WHEN** two candidates contain the same logo occupying substantially different proportions of their frames due to padding
- **THEN** both are reported as matches against the same reference

#### Scenario: Anti-aliased border around content

- **WHEN** a candidate's padding meets its content through faint anti-aliased pixels
- **THEN** the trim still isolates the content
- **AND** the candidate is reported as a match

#### Scenario: Fully opaque image

- **WHEN** a candidate image is fully opaque and padded with a solid colour
- **THEN** it is trimmed to its content bounding box rather than left at full frame

### Requirement: Colour-independent similarity signature

The similarity signature SHALL be computed from luminance so that images identical in layout but different in colour produce the same signature.

Consequently the reference set SHALL require one image per distinct brand layout rather than one per colourway, and recoloured copies of a reference layout SHALL be detected even when that colourway is not present in the reference set.

An exact copy of a reference image SHALL be matched by this same mechanism; no separate exact-match pass is required for detection.

#### Scenario: Recoloured copy of a reference layout

- **WHEN** a repository contains a copy of a reference logo in different colours
- **THEN** it is reported as a match against that reference's label

#### Scenario: Colourway absent from the reference set

- **WHEN** a repository contains a logo in a colourway that appears nowhere in the reference set but whose layout matches a reference
- **THEN** it is reported as a match

#### Scenario: Byte-identical copy

- **WHEN** a repository contains a byte-identical copy of a reference image
- **THEN** it is reported as a match at the closest possible similarity distance

### Requirement: Image source coverage

Image matching SHALL cover common raster image formats, icon-container formats, vector images, and images recovered from base64-encoded data URIs. Vector images SHALL be rasterised before signature computation so that they pass through the same matching path as raster images.

An image that cannot be decoded or rasterised SHALL be skipped with the failure recorded, and MUST NOT end the scan of the containing repository.

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
- **AND** the remaining images in that repository are still matched

### Requirement: Threshold-governed matching with reported distance

A candidate SHALL be reported as a match when its similarity distance to a reference is within the configured threshold. Each match SHALL record the matched reference's label and the measured distance.

Where a candidate is within threshold of more than one reference, matches SHALL be ordered by distance so that the closest reference is presented first.

#### Scenario: Candidate within threshold

- **WHEN** a candidate's distance to a reference is within the configured threshold
- **THEN** it is reported as a match recording that reference's label and the measured distance

#### Scenario: Candidate outside threshold

- **WHEN** a candidate's distance to every reference exceeds the configured threshold
- **THEN** no image match is reported for it

#### Scenario: Candidate close to several references

- **WHEN** a candidate is within threshold of more than one reference
- **THEN** the matches are ordered by increasing distance
- **AND** the closest reference is presented first

### Requirement: Replaceable matching strategy

The matching strategy SHALL be isolated behind a boundary such that an additional strategy can be introduced without altering repository acquisition, configuration, or reporting.

Whole-image signature matching does not detect a logo composited as a small region inside a larger image, because the surrounding content dominates the signature. Detecting that case is out of scope for this change; the boundary exists so it can be added later without disturbing the surrounding capabilities.

#### Scenario: An additional strategy is introduced

- **WHEN** an additional matching strategy is introduced behind the boundary
- **THEN** repository acquisition, configuration, and reporting require no change
- **AND** its matches flow into reporting through the existing finding structure
