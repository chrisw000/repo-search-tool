## MODIFIED Requirements

### Requirement: Font name and font reference coverage

The system SHALL detect references to brand fonts. Coverage SHALL include
font-family declarations, font-face declarations, references to embedded font
files by their file extensions, and links to externally hosted font services.

A reference to a font asset — an embedded font file, or a link to an externally
hosted font service — SHALL be attributed to the brand when the matched text
carries a configured brand font name, and SHALL be reported as a brand finding
identifying the font that attributed it.

A reference to a font asset that carries no configured brand font name SHALL
still be reported, at a lower severity than an attributed one, and SHALL be
attributed to a distinct search-group whose description and remediation state
that the asset was found rather than matched against the brand, and that a human
must establish whether the family is a brand font. It MUST NOT be reported as a
brand finding, and it MUST NOT be silently discarded: a brand font file
frequently carries no brand string in its name, so the unattributed set is the
only place such a file can surface.

A single font asset reference SHALL be reported once. A reference attributed to
the brand MUST NOT also be reported as an unattributed one.

#### Scenario: Font declared in a stylesheet

- **WHEN** a stylesheet declares a brand font in a font-family or font-face declaration
- **THEN** a finding is recorded at that line

#### Scenario: Embedded font file referenced

- **WHEN** a file references a font asset by a recognised font file extension
- **THEN** a finding is recorded at that line

#### Scenario: Font file named after a brand font

- **WHEN** a file references a font asset whose path carries a configured brand font name
- **THEN** a brand font finding is recorded at that line with the severity configured for attributed font references
- **AND** the recorded excerpt carries the asset reference that named the brand font
- **AND** no unattributed font asset finding is recorded for the same reference

#### Scenario: Font file carrying no brand font name

- **WHEN** a file references a font asset whose path carries no configured brand font name
- **THEN** a finding is recorded at that line attributed to the unattributed font asset group
- **AND** its severity is lower than that of an attributed font reference
- **AND** it is not recorded as a brand font finding

#### Scenario: Externally hosted font service referenced

- **WHEN** a file links to an external font-hosting service carrying a brand font
- **THEN** a finding is recorded at that line

#### Scenario: External font service link naming a brand font

- **WHEN** a file links to an external font-hosting service and the link names a configured brand font
- **THEN** the finding is attributed to the brand on the same terms as an embedded font file naming that font

#### Scenario: External font service link naming no brand font

- **WHEN** a file links to an external font-hosting service and the link names no configured brand font
- **THEN** the finding is recorded as an unattributed font asset rather than a brand finding

#### Scenario: Well-known third-party font package

- **WHEN** a file references a font asset belonging to a third-party icon or font package that the configuration excludes by match text
- **THEN** no unattributed font asset finding is recorded for it
- **AND** a reference to that same package that does carry a configured brand font name is still reported as a brand finding

## ADDED Requirements

### Requirement: Match-text exclusions applied during search

Where a search-group declares expressions that exclude a match by its matched
text, the system SHALL evaluate them against the text a pattern matched, and
SHALL discard the match when any of them matches. A discarded match SHALL leave
no finding, no excerpt, and no contribution to any count.

Exclusion SHALL be evaluated per match rather than per line or per file, so that
one excluded match on a line MUST NOT suppress a different, unexcluded match on
that same line — including a match by another pattern in the same group.

Exclusions SHALL apply only to the group that declares them, and SHALL be
matched with the same case sensitivity as that group's patterns.

#### Scenario: Match excluded by its text

- **WHEN** a group's pattern matches text that one of that group's exclusion expressions also matches
- **THEN** no finding is recorded for that match

#### Scenario: Two matches on one line, one excluded

- **WHEN** a line contains one match that an exclusion expression matches and one that it does not
- **THEN** a finding is recorded for the match that was not excluded
- **AND** no finding is recorded for the excluded one

#### Scenario: Exclusions are group-local

- **WHEN** one group declares exclusion expressions and another group's patterns match the same text
- **THEN** the other group still records its finding

#### Scenario: Exclusion case sensitivity follows the group

- **WHEN** a group is case-insensitive and its exclusion expression differs from the matched text only in case
- **THEN** the match is excluded
