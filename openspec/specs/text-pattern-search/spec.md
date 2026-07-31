# text-pattern-search Specification

## Purpose
Finds textual traces of the old brand — names, fonts, domains, colours, legal strings — wherever they appear in a repository's files, including inside markup attributes and inside base64-encoded image data. Text search complements image matching: much brand residue is never an image file at all.

## Requirements

### Requirement: Search-group execution over in-scope files

The system SHALL evaluate every configured search-group against every file within that group's effective scope, for each scanned repository.

Each match SHALL capture the file path relative to the repository root, the line number, the name of the search-group that matched, the severity of that group, and surrounding context lines sufficient to judge the match without opening the file.

#### Scenario: Pattern matches within a scoped file

- **WHEN** a file within a search-group's scope contains text matching one of that group's patterns
- **THEN** a finding is recorded with the relative path, line number, matching group name, that group's severity, and surrounding context

#### Scenario: Multiple matches in a single file

- **WHEN** a file contains several matches
- **THEN** each match is recorded separately with its own line number

#### Scenario: File outside a group's scope

- **WHEN** a file contains text matching a group's patterns but lies outside that group's scope
- **THEN** no finding is recorded for that group

### Requirement: Brand-name coverage including markup

Brand-name detection SHALL cover occurrences in prose and code, and SHALL additionally cover occurrences embedded in markup where a brand reference is carried by an attribute or element rather than by visible body text. This SHALL include image alternative-text attributes, CSS class and identifier names, and SVG title and description elements.

#### Scenario: Brand name in image alternative text

- **WHEN** markup contains an image whose alternative-text attribute carries the brand name
- **THEN** a finding is recorded at that line

#### Scenario: Brand name in a CSS class name

- **WHEN** a stylesheet or markup file uses a class or identifier name containing the brand name
- **THEN** a finding is recorded at that line

#### Scenario: Brand name in an SVG title

- **WHEN** an SVG contains a title or description element carrying the brand name
- **THEN** a finding is recorded at that line

### Requirement: Font name and font reference coverage

The system SHALL detect references to brand fonts. Coverage SHALL include font-family declarations, font-face declarations, references to embedded font files by their file extensions, and links to externally hosted font services.

#### Scenario: Font declared in a stylesheet

- **WHEN** a stylesheet declares a brand font in a font-family or font-face declaration
- **THEN** a finding is recorded at that line

#### Scenario: Embedded font file referenced

- **WHEN** a file references a font asset by a recognised font file extension
- **THEN** a finding is recorded at that line

#### Scenario: Externally hosted font service referenced

- **WHEN** a file links to an external font-hosting service carrying a brand font
- **THEN** a finding is recorded at that line

### Requirement: Legacy domain and brand colour coverage

The system SHALL detect references to legacy brand domains and URLs, and occurrences of brand colours. Colour detection SHALL recognise equivalent notations of the same colour, not only one spelling.

#### Scenario: Legacy domain referenced

- **WHEN** a file contains a legacy brand domain or a URL on that domain
- **THEN** a finding is recorded at that line

#### Scenario: Brand colour in hexadecimal notation

- **WHEN** a file contains a brand colour written in hexadecimal notation
- **THEN** a finding is recorded at that line

#### Scenario: Same brand colour in functional notation

- **WHEN** a file contains that same brand colour written in a functional colour notation instead of hexadecimal
- **THEN** a finding is recorded at that line

### Requirement: Legal and trademark string coverage

The system SHALL detect legal and trademark strings associated with the old brand, such as legal entity names and trademark or copyright notices.

#### Scenario: Trademark notice present

- **WHEN** a file contains a trademark or copyright notice naming the old brand
- **THEN** a finding is recorded at that line with the configured severity for that group

### Requirement: Base64-embedded image discovery

The system SHALL detect images embedded directly in text files as base64-encoded data URIs. Each such image SHALL be decoded and submitted to image-similarity matching, so that an inlined logo is detected by its content rather than merely noted as an encoded blob.

A base64 payload that cannot be decoded or is not a recognisable image SHALL be skipped without ending the scan of that file or repository.

#### Scenario: Inlined image matches a reference

- **WHEN** a text file contains a base64-encoded image data URI whose decoded content matches a reference image
- **THEN** an image match finding is recorded, identifying the containing file and the line of the data URI
- **AND** the finding names the matched reference label

#### Scenario: Inlined image matches nothing

- **WHEN** a base64-encoded image decodes successfully but matches no reference image
- **THEN** no image match finding is recorded for it

#### Scenario: Undecodable base64 payload

- **WHEN** a base64 payload cannot be decoded or is not a recognisable image
- **THEN** it is skipped
- **AND** the scan of the containing file and repository continues
