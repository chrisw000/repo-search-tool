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

The breakdown by search-group and reference label SHALL additionally state, for each row, the severity that row's findings carry: for a search-group, the severity configured against that group; for a reference label, the severity image matches carry. A reader SHALL be able to tell a high-severity group from a low-severity one without opening the configuration or any per-repository report.

Each row SHALL be expanded to show what was actually matched beneath it:

- for a search-group, the distinct matched values found under that group across all repositories, each with the number of findings it accounts for, ordered by frequency with the most common first;
- for a reference label, the distribution of its findings across likeness confidence bands.

Where a group has more distinct matched values than the summary presents, the expansion SHALL state how many further values were omitted, so a truncated list is never mistaken for a complete one. Distinct matched values SHALL be grouped in a way that respects the group's own case sensitivity: a case-insensitive group's spellings SHALL be counted as one value, and a case-sensitive group's SHALL be kept apart.

#### Scenario: Breakdown by group and reference label

- **WHEN** the executive summary is read
- **THEN** it shows how many findings each search-group and each reference label produced across all repositories

#### Scenario: Breakdown by severity

- **WHEN** the executive summary is read
- **THEN** it shows the distribution of findings across severities

#### Scenario: Configured severity shown against each group

- **WHEN** a search-group configured as high severity and one configured as low severity both produced findings
- **THEN** each appears in the breakdown carrying its own configured severity

#### Scenario: Matched values shown for a search-group

- **WHEN** a search-group produced findings whose matched text differed
- **THEN** the breakdown lists those distinct matched values with the number of findings each accounts for
- **AND** the most frequent value is presented first

#### Scenario: Many distinct matched values

- **WHEN** a search-group produced more distinct matched values than the summary presents
- **THEN** the listed values are the most frequent ones
- **AND** the number of further values not listed is stated

#### Scenario: Case-insensitive group's spellings

- **WHEN** a case-insensitive search-group matched the same value in several spellings
- **THEN** those spellings are counted as one matched value

#### Scenario: Case-sensitive group's spellings

- **WHEN** a case-sensitive search-group matched values differing only in case
- **THEN** they are counted as distinct matched values

### Requirement: Likeness confidence bands for image matches

The executive summary SHALL band image findings by the likeness of the match, derived from the measured similarity distance, so that an exact logo hit is distinguishable from a candidate that matched only just within the configured threshold. The bands SHALL be ordered from most to least confident and SHALL be named in plain language rather than by distance alone.

Band boundaries SHALL be fixed in absolute distance, so that a given distance falls in the same band in every run regardless of the threshold that run used. A band whose whole distance range lies beyond the configured similarity threshold SHALL be omitted, because no finding in that run could ever fall in it; a band that the threshold covers even partly SHALL be shown, including when it holds no findings.

The distance range each band covers SHALL be stated alongside the bands, so a reader can see what the confidence labels mean, and the configured similarity threshold SHALL be stated with them, because it governs which bands were reachable at all.

#### Scenario: Image findings banded by likeness

- **WHEN** a reference label produced findings at differing similarity distances
- **THEN** the breakdown shows how many of its findings fall in each confidence band

#### Scenario: Closest matches in the most confident band

- **WHEN** an image matched a reference at or near zero distance
- **THEN** that finding falls in the most confident band

#### Scenario: Bands unreachable at the configured threshold

- **WHEN** a band's whole distance range lies beyond the configured similarity threshold
- **THEN** that band is not shown

#### Scenario: Reachable band with no findings

- **WHEN** a band lies within the configured similarity threshold but no finding fell in it
- **THEN** the band is still shown, carrying a count of zero

#### Scenario: Band meanings stated

- **WHEN** the executive summary presents confidence bands
- **THEN** the distance range each band covers is stated
- **AND** the configured similarity threshold is stated

### Requirement: Drill-through to per-repository reports

Every repository listed in the executive summary SHALL link to its own per-repository report, so the summary can be used as the navigation entry point into the detail.

#### Scenario: Following a link from the summary

- **WHEN** a repository listed in the executive summary is followed
- **THEN** it leads to that repository's own report

#### Scenario: Skipped repository listed

- **WHEN** a skipped or failed repository is listed in the executive summary
- **THEN** it links to its report and the reason is visible

### Requirement: Summary rendered as HTML alongside Markdown

The system SHALL emit the executive summary as an HTML document in addition to the Markdown one, covering the same run and carrying the same sections, the same totals, and the same rows. Neither rendering SHALL be a subset of the other.

The HTML SHALL be self-contained: it SHALL render fully with no network access and no companion asset file, so that the output directory can be copied or shared and still be readable.

The HTML SHALL distinguish severities and confidence bands visually, and SHALL remain legible without relying on colour alone to convey either.

Links from the HTML summary to per-repository reports SHALL resolve from the summary's own location, as the Markdown summary's links do.

#### Scenario: HTML emitted with the Markdown

- **WHEN** a run completes
- **THEN** an HTML executive summary is written alongside the Markdown one

#### Scenario: The two renderings agree

- **WHEN** the HTML and Markdown summaries for one run are compared
- **THEN** they report the same totals, the same ranked repositories, and the same breakdown rows

#### Scenario: Opened without network access

- **WHEN** the HTML summary is opened with no network access
- **THEN** it renders fully, with no reference to any external stylesheet, script, font, or image

#### Scenario: Severity and confidence distinguishable without colour

- **WHEN** the HTML summary is read without colour perception
- **THEN** each severity and each confidence band remains identifiable from its text

#### Scenario: Drill-through from the HTML summary

- **WHEN** a repository listed in the HTML summary is followed
- **THEN** it leads to that repository's own report
