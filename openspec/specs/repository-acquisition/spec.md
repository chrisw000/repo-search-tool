# repository-acquisition Specification

## Purpose
Obtains a local, scannable copy of every target repository across multiple GitHub hosts and organisations, so that content-based scanning has something to read. Acquisition must survive unattended runs over hundreds of repositories, resume after interruption, and never damage a working copy it does not own.

## Requirements

### Requirement: Multi-host authentication preflight

The system SHALL verify, before acquiring any repository, that an authenticated session exists for every configured host AND that every configured organisation on that host can be enumerated. The system SHALL abort the run when any host or organisation fails this check, and SHALL report the failing host and organisation together with a remediation command.

The presence of an installed CLI or a non-empty credential SHALL NOT by itself be treated as proof of access, because a token can be valid yet not authorised for a given organisation.

#### Scenario: All hosts and organisations reachable

- **WHEN** the preflight runs and every configured host has an authenticated session and every configured organisation is enumerable
- **THEN** the system proceeds to acquisition

#### Scenario: A host has no authenticated session

- **WHEN** the preflight finds no authenticated session for a configured host
- **THEN** the system aborts before acquiring any repository
- **AND** reports the host name and a remediation command naming that host

#### Scenario: Session valid but organisation not authorised

- **WHEN** a host has an authenticated session but a configured organisation cannot be enumerated
- **THEN** the system aborts before acquiring any repository
- **AND** reports which organisation on which host failed, distinguishing this from a missing session

### Requirement: Target enumeration across hosts and organisations

The system SHALL accept multiple `{host, organisation}` targets and enumerate all repositories in each. Enumeration SHALL be complete: results MUST NOT be truncated by result-page limits. Archived repositories and forks SHALL be excluded by default and includable by configuration.

#### Scenario: Organisation exceeds a single result page

- **WHEN** an organisation contains more repositories than one result page returns
- **THEN** the system enumerates every repository across all pages
- **AND** the count of enumerated repositories equals the organisation's total matching repository count

#### Scenario: Archived and forked repositories by default

- **WHEN** an organisation contains archived repositories and forks and no inclusion option is configured
- **THEN** neither archived repositories nor forks are enumerated as targets

#### Scenario: Archived repositories explicitly included

- **WHEN** the configuration opts in to archived repositories
- **THEN** archived repositories are enumerated as targets

### Requirement: Named repository selection within a target

A `{host, organisation}` target SHALL optionally name a subset of repositories to acquire. When a subset is named, the system SHALL acquire only those repositories and MUST NOT enumerate the rest of the organisation.

Naming a repository is an explicit request for it, so a named repository SHALL be acquired even when it is archived or a fork and the corresponding inclusion option is off.

A named repository that cannot be found or accessed SHALL be recorded as an acquisition failure against that repository. It MUST NOT silently reduce the target set, because a trial run that quietly scans four of five named repositories gives false confidence in the result.

#### Scenario: A subset of an organisation is named

- **WHEN** a target names a subset of repositories in its organisation
- **THEN** only the named repositories are acquired and scanned
- **AND** the rest of the organisation is not enumerated

#### Scenario: No subset named

- **WHEN** a target names no subset
- **THEN** every repository in the organisation is enumerated as before

#### Scenario: A named repository does not exist

- **WHEN** a named repository cannot be found on its host
- **THEN** it is recorded as an acquisition failure giving the reason
- **AND** the other named repositories are still acquired and scanned

#### Scenario: A named repository is archived

- **WHEN** a named repository is archived and archived repositories are not otherwise included
- **THEN** it is still acquired, because naming it is an explicit request for it

#### Scenario: A named repository has an uncommon default branch

- **WHEN** a named repository's default branch is not the most common default
- **THEN** its actual default branch is resolved and scanned

### Requirement: Default branch resolution

The system SHALL resolve each repository's actual default branch and scan that branch. The system MUST NOT assume any particular branch name.

#### Scenario: Repository whose default branch is not the common default

- **WHEN** a repository's default branch is named something other than the most common default
- **THEN** the system acquires and scans that repository's actual default branch
- **AND** records the branch name used

### Requirement: Managed clone acquisition and refresh

For repositories the system clones into its own managed location, the system SHALL acquire only the content of the default branch tip, without repository history. On a subsequent run against an existing managed clone, the system SHALL update it to the current default-branch tip and discard any local divergence, so that every scan reflects current HEAD.

Before updating an existing managed directory, the system SHALL confirm the directory corresponds to the intended repository. A directory that does not SHALL be recorded as an acquisition failure rather than updated.

#### Scenario: First acquisition of a repository

- **WHEN** no managed clone exists for a target repository
- **THEN** the system acquires the default branch content without history
- **AND** records the commit identifier acquired

#### Scenario: Re-run against an existing managed clone

- **WHEN** a managed clone already exists and the remote default branch has advanced
- **THEN** the system updates the clone to the current default-branch tip
- **AND** the scanned content matches the current tip with no leftover local modifications or untracked files

#### Scenario: Managed directory points at a different repository

- **WHEN** an existing managed directory does not correspond to the intended repository
- **THEN** the system records an acquisition failure for that repository
- **AND** does not update or scan that directory

### Requirement: Non-destructive handling of external clones

The system SHALL support scanning user-supplied, pre-existing local repository directories. The system MUST NOT modify such directories in any way.

A user-supplied directory with no uncommitted modifications SHALL be scanned as it currently stands, and the commit identifier scanned SHALL be recorded so that staleness is visible. A user-supplied directory with uncommitted modifications SHALL be skipped, with the reason recorded, rather than reset.

#### Scenario: Clean external directory

- **WHEN** a user-supplied directory has no uncommitted modifications
- **THEN** the system scans it at its currently checked-out commit without modifying it
- **AND** records that commit identifier

#### Scenario: External directory with uncommitted work

- **WHEN** a user-supplied directory has uncommitted modifications
- **THEN** the system skips it and records a warning giving the reason
- **AND** the directory's contents and checked-out state are left untouched

### Requirement: Per-repository failure isolation

A failure affecting one repository SHALL NOT end the run or prevent any other repository from being acquired and scanned. Each failure SHALL be recorded against the repository it affected, with the reason, and SHALL be surfaced in reporting.

#### Scenario: One repository fails mid-run

- **WHEN** acquisition of one repository fails during a run over many repositories
- **THEN** the run continues with the remaining repositories
- **AND** the failure and its reason are recorded against the affected repository

### Requirement: Resumable runs

The system SHALL checkpoint run progress such that an interrupted run can be resumed without redoing completed work. On resume, repositories already completed SHALL NOT be re-acquired or re-scanned unless a refresh is requested.

#### Scenario: Run interrupted and resumed

- **WHEN** a run is interrupted after completing part of the target set and is then resumed
- **THEN** the system continues from the uncompleted repositories
- **AND** already-completed repositories are not scanned again
- **AND** the final results cover the full target set
