# executive-summary Specification

## Purpose
Turns hundreds of per-repository reports into a single document that answers the questions an owner of the rebrand actually asks: how much is there, where is it worst, and what kind of work is it. It is the entry point to the per-repository detail, not a replacement for it.

## Requirements

### Requirement: Single cross-repository rollup

The system SHALL emit exactly one executive summary per run, covering every repository in that run's target set.

#### Scenario: Run over many repositories

- **WHEN** a run completes over a set of target repositories
- **THEN** one executive summary is emitted
- **AND** it accounts for every repository in the target set

### Requirement: Run totals

The executive summary SHALL report the totals for the run: how many repositories were scanned, how many were clean, how many had findings, and how many were skipped or failed. These counts SHALL reconcile with the target set, so that no repository is silently unaccounted for.

#### Scenario: Totals reported

- **WHEN** the executive summary is read
- **THEN** it states the number of repositories scanned, clean, with findings, and skipped or failed

#### Scenario: Counts reconcile

- **WHEN** the reported category counts are summed
- **THEN** they account for every repository in the target set

### Requirement: Repositories ranked by remediation weight

The executive summary SHALL rank repositories that have findings by remediation weight, derived from both the severity of their findings and the number of them, presenting the heaviest first so that the summary serves as a triage order.

#### Scenario: Ranking presented

- **WHEN** several repositories have findings
- **THEN** they are listed in order of remediation weight with the heaviest first

#### Scenario: Severity outweighs raw count

- **WHEN** one repository has few high-severity findings and another has many low-severity findings
- **THEN** the ranking reflects severity rather than ordering purely by count

#### Scenario: Clean repositories in the ranking

- **WHEN** repositories without findings exist
- **THEN** they do not occupy the ranked remediation list
- **AND** they remain accounted for in the run totals

### Requirement: Breakdown by match type and severity

The executive summary SHALL break down findings across all repositories both by match type — including which search-group or reference label produced them — and by severity.

#### Scenario: Breakdown by group and reference label

- **WHEN** the executive summary is read
- **THEN** it shows how many findings each search-group and each reference label produced across all repositories

#### Scenario: Breakdown by severity

- **WHEN** the executive summary is read
- **THEN** it shows the distribution of findings across severities

### Requirement: Drill-through to per-repository reports

Every repository listed in the executive summary SHALL link to its own per-repository report, so the summary can be used as the navigation entry point into the detail.

#### Scenario: Following a link from the summary

- **WHEN** a repository listed in the executive summary is followed
- **THEN** it leads to that repository's own report

#### Scenario: Skipped repository listed

- **WHEN** a skipped or failed repository is listed in the executive summary
- **THEN** it links to its report and the reason is visible
