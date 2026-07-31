## ADDED Requirements

### Requirement: Unread inputs reported with their cause

Every report SHALL list the files within that repository that could not be read, and SHALL state for each one why it could not be read, using the classification recorded during the scan.

The report SHALL present this list as unassessed rather than clean, so that a reader cannot mistake a file the system failed to open for a file the system opened and found nothing in.

Where a cause implies a different remedy from repairing the file — content that was never fetched, or a placeholder awaiting artwork — the report SHALL make that remedy legible rather than presenting every entry as a defect of the same kind.

A repository whose only anomalies are unread inputs SHALL still be reported as clean with respect to findings, because no brand residue was found in what was read, but its unread inputs SHALL remain visible in the report.

#### Scenario: Report lists an unreadable file

- **WHEN** a repository contains a file that could not be read
- **THEN** its report lists that file with the reason it could not be read
- **AND** the section is presented as unassessed rather than clean

#### Scenario: Causes are distinguished in the report

- **WHEN** a repository contains an empty placeholder, a pointer to unfetched content, and a malformed image
- **THEN** the report distinguishes the three
- **AND** each states what would be needed to assess it

#### Scenario: Machine-readable form carries the same classification

- **WHEN** a report's machine-readable form is inspected
- **THEN** each unread input carries the same classification as the human-readable report
- **AND** no unread input is present in one form and absent from the other

#### Scenario: Clean repository that contains unread inputs

- **WHEN** a repository yields no findings but contains files that could not be read
- **THEN** its report states that no brand residue was found in what was read
- **AND** the unread inputs are still listed with their causes
