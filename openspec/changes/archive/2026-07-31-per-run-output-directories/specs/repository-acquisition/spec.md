## MODIFIED Requirements

### Requirement: Resumable runs

The system SHALL checkpoint run progress such that an interrupted run can be resumed without redoing completed work. On resume, repositories already completed SHALL NOT be re-acquired or re-scanned unless a refresh is requested.

A checkpoint SHALL belong to exactly one run and SHALL be held with that run's artifacts. Resuming SHALL continue the run the checkpoint belongs to, adding to that run's reports. A run that is not resuming another SHALL begin with no completed repositories, regardless of what earlier runs completed, so that its results describe the repositories it scanned itself rather than inheriting an earlier run's.

A repository restored from a checkpoint SHALL be accounted for in that run's totals exactly as one scanned during it, so that resumption never leaves a repository unaccounted for.

#### Scenario: Run interrupted and resumed

- **WHEN** a run is interrupted after completing part of the target set and is then resumed
- **THEN** the system continues from the uncompleted repositories
- **AND** already-completed repositories are not scanned again
- **AND** the final results cover the full target set

#### Scenario: A new run does not inherit an earlier run's progress

- **WHEN** a new run is started against an output root where an earlier run completed the same repositories
- **THEN** every repository in the new run's target set is acquired and scanned again
- **AND** the new run's results are written as its own, leaving the earlier run's untouched

#### Scenario: Refresh requested

- **WHEN** a run is asked to refresh repositories completed by an earlier run
- **THEN** those repositories are re-acquired and re-scanned
- **AND** their results are recorded against the run that re-scanned them
