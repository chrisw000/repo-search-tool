# run-output-layout Specification

## Purpose
Governs where a run's artifacts are written and how one run's output is kept separate from another's, so that successive scans over the same repositories can be compared rather than overwriting one another. It also fixes what deliberately is not per-run — the repository clones, which are shared working copies rather than evidence of a particular run.

## Requirements

### Requirement: Per-run output directory

Every run SHALL write its artifacts into a directory of its own beneath the configured output root. A run's per-repository reports, its executive summary in every rendering, its checkpoint, and its run log SHALL all be written within that directory.

A run MUST NOT write any of those artifacts to a path shared with another run, so that completing a run never destroys the artifacts of an earlier one.

Run directories SHALL be named from the run's start instant in a form that sorts chronologically when ordered by name, so that the order runs were taken is legible from the directory listing alone. Two runs starting within the same named instant SHALL be given distinct directories rather than sharing one.

#### Scenario: Two runs over one output root

- **WHEN** a run completes and a second run is then taken against the same output root
- **THEN** each run's reports and executive summary exist in its own run directory
- **AND** the first run's artifacts are unchanged by the second

#### Scenario: Run directories ordered by name

- **WHEN** several run directories exist under one output root
- **THEN** ordering them by name orders them by the time their runs started

#### Scenario: Two runs starting in the same named instant

- **WHEN** a run starts while an existing run directory already bears the name derived from its start instant
- **THEN** the new run is given a distinct directory
- **AND** neither run writes into the other's directory

### Requirement: Links within a run resolve inside that run

The executive summary's links to per-repository reports SHALL resolve to the reports produced by the same run. A summary MUST NOT link to a report produced by any other run.

#### Scenario: Drill-through after a later run

- **WHEN** a repository is followed from the executive summary of an earlier run, after a later run has produced its own reports
- **THEN** it leads to that repository's report as that earlier run produced it

### Requirement: Repository clones are shared across runs

Repository clones SHALL be held outside every run directory, at the output root, and SHALL be reused across runs. Starting a new run MUST NOT copy, move, or delete them.

Clones are working copies rather than evidence: a clone reflects the repository as it stands now, and every run reads whatever the clone holds at the moment it is scanned. What the run observed there is recorded in that run's reports, which is where the per-run evidence belongs.

#### Scenario: Second run reuses existing clones

- **WHEN** a second run is taken against an output root whose clones already exist
- **THEN** it acquires into those same clones rather than cloning afresh into its run directory

#### Scenario: Clones survive a new run

- **WHEN** a new run directory is created
- **THEN** the existing clones are neither deleted nor duplicated

### Requirement: Run record

Every run directory SHALL carry a machine-readable record identifying the run it holds: the run's identifier, the instant it started, the version of the tool that produced it, the configuration source it read, and the acquisition mode it ran in. The record SHALL state whether the run finished, and when it finished, so that a run interrupted partway is distinguishable from one that ran to completion.

The record MUST NOT be the source of any finding count or other rollup figure. Those belong to the executive summary, which is rendered from a single model precisely so that its forms cannot disagree; a second, separately-computed statement of the same figures would reintroduce that risk.

#### Scenario: Completed run identified

- **WHEN** a run completes and its run directory is inspected
- **THEN** the record states the run identifier, start instant, tool version, configuration source, and mode
- **AND** it states that the run finished, and when

#### Scenario: Interrupted run identified

- **WHEN** a run is interrupted before completing and its run directory is inspected
- **THEN** the record states that the run has not finished

### Requirement: Run selection on re-invocation

When invoked without being told which run to use, the system SHALL continue the most recent unfinished run under the output root, and SHALL start a new run when the most recent run finished or when no run exists.

A run started fresh MUST NOT read another run's checkpoint or reports. An operator SHALL be able to name a run directory outright, in which case that run is used whether or not it finished, and MUST be able to force a new run when the most recent one is unfinished.

Requesting that completed repositories be scanned again is a request for a new run's worth of results, and SHALL therefore start a new run.

#### Scenario: Interrupted run resumed by re-running the same command

- **WHEN** a run is interrupted and the same command is invoked again
- **THEN** the unfinished run is continued in its own directory
- **AND** repositories it already completed are not scanned again

#### Scenario: Re-run after a completed run

- **WHEN** the same command is invoked again after the previous run finished
- **THEN** a new run directory is created
- **AND** the previous run's reports and summary remain as that run left them

#### Scenario: A named run is used outright

- **WHEN** an existing run directory is named on invocation
- **THEN** that run's directory is used, whether or not that run had finished

#### Scenario: Re-scanning completed repositories

- **WHEN** a run is invoked asking that already-completed repositories be scanned again
- **THEN** a new run directory is created rather than the previous run's being overwritten

#### Scenario: First run under an output root holding earlier artifacts

- **WHEN** a run is taken against an output root that holds artifacts written before run directories existed
- **THEN** a new run directory is created
- **AND** those earlier artifacts are neither read nor modified
