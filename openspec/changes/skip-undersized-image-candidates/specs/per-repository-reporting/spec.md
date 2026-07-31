## MODIFIED Requirements

### Requirement: Provenance block

Every report SHALL carry a provenance block recording the conditions under which it was produced, sufficient to reproduce and audit the scan. It SHALL record the search-groups executed, the reference-image labels searched for, the similarity threshold used, the minimum candidate image size in force, the repository's scanned commit identifier and branch name, the time of the scan, and the version of the tool.

Where a rule ruled candidate images out of assessment, the report SHALL also record how many were ruled out, so that a shrinking count of images examined is explicable from the report itself rather than only by comparison with another run. The ruled-out images SHALL be recorded as a count and MUST NOT be enumerated file by file.

Both forms of the report SHALL agree on these values.

#### Scenario: Report inspected for provenance

- **WHEN** a report is inspected
- **THEN** it states the search-groups executed, reference labels searched, similarity threshold, minimum candidate image size, scanned commit and branch, scan timestamp, and tool version

#### Scenario: Non-default threshold used

- **WHEN** a scan runs with a threshold other than the default
- **THEN** the provenance block records the value actually used

#### Scenario: Repository containing undersized images

- **WHEN** a scanned repository contains images ruled out by the minimum candidate image size
- **THEN** its report records how many were ruled out and the minimum that ruled them out
- **AND** they are not counted among the images examined
- **AND** they are not listed individually

#### Scenario: Machine-readable form inspected

- **WHEN** a report's machine-readable form is inspected
- **THEN** it carries the same minimum and the same ruled-out count as the human-readable report
