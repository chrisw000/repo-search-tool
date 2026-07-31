# per-repository-reporting Specification

## Purpose
Produces the per-repository artifact that is the actual hand-off of this tool: a report an AI coding agent can read and act on to perform the rebrand fixes, backed by a machine-readable sidecar. Because the report is consumed downstream rather than merely read by a human, its structure is a contract.

## Requirements

### Requirement: One report per repository in two forms

The system SHALL emit, for every repository in the target set, one human- and agent-readable Markdown report and one machine-readable JSON sidecar.

The two forms SHALL describe the same findings. The sidecar MUST NOT omit findings present in the Markdown report.

#### Scenario: Repository with findings

- **WHEN** a scanned repository yields findings
- **THEN** a Markdown report and a JSON sidecar are emitted for it
- **AND** the findings in the sidecar correspond to those in the Markdown report

#### Scenario: Every target repository covered

- **WHEN** a run completes over a set of target repositories
- **THEN** every repository in that set has a report, including those that were clean, skipped, or failed

### Requirement: Reports are actionable fix instructions

The Markdown report SHALL present findings as actionable remediation instructions, organised so that a reader can act on them directly. It MUST NOT be an undifferentiated dump of raw matches.

#### Scenario: Report consumed as fix instructions

- **WHEN** a Markdown report containing findings of several types is read
- **THEN** findings are grouped and presented so that each states what was found, where, and what needs to change

### Requirement: Finding content

Each finding SHALL carry:

- the type of match, distinguishing a text-pattern match from an image match
- the matched search-group name, for a text match, or the matched reference-image label, for an image match
- the file path relative to the repository root
- the line number, where the match type has one
- the severity attributed to the match
- a permalink resolving to the matched content on its host, pinned to the scanned commit and, where applicable, the line
- for an image match, the measured similarity distance

#### Scenario: Text-pattern finding

- **WHEN** a text-pattern match is reported
- **THEN** it carries the match type, matched group name, relative path, line number, severity, and a permalink pinned to the scanned commit and line

#### Scenario: Image finding

- **WHEN** an image match is reported
- **THEN** it carries the match type, matched reference label, relative path, severity, measured distance, and a permalink pinned to the scanned commit

#### Scenario: Permalink pinned to scanned state

- **WHEN** a permalink in a report is followed after the repository's default branch has advanced
- **THEN** it resolves to the content as it stood at the scanned commit, not to a moved or absent line

### Requirement: Provenance block

Every report SHALL carry a provenance block recording the conditions under which it was produced, sufficient to reproduce and audit the scan. It SHALL record the search-groups executed, the reference-image labels searched for, the similarity threshold used, the repository's scanned commit identifier and branch name, the time of the scan, and the version of the tool.

#### Scenario: Report inspected for provenance

- **WHEN** a report is inspected
- **THEN** it states the search-groups executed, reference labels searched, similarity threshold, scanned commit and branch, scan timestamp, and tool version

#### Scenario: Non-default threshold used

- **WHEN** a scan runs with a threshold other than the default
- **THEN** the provenance block records the value actually used

### Requirement: Clean, skipped, and failed repositories reported explicitly

A repository that yields no findings SHALL be reported explicitly as clean, so that "no findings" is distinguishable from "not scanned".

A repository that was skipped or failed SHALL be reported with the reason, and MUST NOT be presented as clean.

#### Scenario: Repository with no findings

- **WHEN** a repository is scanned successfully and yields no findings
- **THEN** its report states explicitly that it is clean

#### Scenario: Repository skipped for uncommitted changes

- **WHEN** a repository is skipped because a user-supplied directory had uncommitted modifications
- **THEN** its report states that it was skipped and gives that reason
- **AND** it is not reported as clean

#### Scenario: Repository failed during acquisition

- **WHEN** acquisition of a repository failed
- **THEN** its report states the failure and its reason
- **AND** it is not reported as clean

### Requirement: Collision-safe report identity

Report output SHALL be organised by host, organisation, and repository name so that repositories sharing a name across different organisations or different hosts do not overwrite one another.

#### Scenario: Same repository name on two hosts

- **WHEN** two scanned repositories share a name but belong to different hosts
- **THEN** each has its own report
- **AND** neither overwrites the other

#### Scenario: Same repository name in two organisations on one host

- **WHEN** two scanned repositories share a name but belong to different organisations on the same host
- **THEN** each has its own report

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
