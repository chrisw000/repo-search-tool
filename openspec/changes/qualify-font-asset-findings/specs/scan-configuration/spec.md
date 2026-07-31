## MODIFIED Requirements

### Requirement: Default search-groups seeded

The configuration SHALL be seeded with default search-groups covering brand
names, font names, brand-attributed font references, unattributed font assets,
legacy domains, brand colours, and legal or trademark strings. These defaults
SHALL be editable and removable like any other group.

The brand-attributed font reference group and the unattributed font asset group
SHALL be seeded at different severities, the unattributed group being the lower
of the two, so that a font asset the scan could not tie to the brand does not
rank alongside one it could.

The unattributed font asset group SHALL be seeded with match-text exclusions
covering well-known third-party icon and font packages, and covering anything
the brand-attributed group already reports. These seeded exclusions SHALL be
editable and removable by configuration like any other field of any other group,
so that the full inventory of font assets can be restored without a code change.

#### Scenario: Default groups present without customisation

- **WHEN** a scan runs against a seeded configuration with no user-added groups
- **THEN** the brand-name, font-name, attributed font-reference, unattributed
  font-asset, legacy-domain, brand-colour, and legal-string groups are all executed

#### Scenario: Seeded font-asset exclusions cleared

- **WHEN** the configuration overrides the unattributed font asset group with an empty set of match-text exclusions
- **THEN** font assets belonging to third-party icon and font packages are reported again
- **AND** no code change was required to restore them

#### Scenario: Seeded font-asset group disabled

- **WHEN** the configuration disables the unattributed font asset group
- **THEN** no unattributed font asset findings are recorded
- **AND** brand-attributed font references are still reported

#### Scenario: No brand fonts configured

- **WHEN** the brand vocabulary configures no fonts
- **THEN** no font asset reference can be attributed to the brand
- **AND** font asset references are reported as unattributed rather than being dropped

## ADDED Requirements

### Requirement: Match-text exclusions declarable on a search-group

A search-group SHALL be able to declare exclusions that veto a match by the text
that matched, as distinct from its file-scope globs, which select the files a
group is evaluated against and cannot express "not this string".

Match-text exclusions SHALL be available to every search-group on identical
terms, seeded or user-defined, because a seeded group is an ordinary group and
MUST NOT enjoy capabilities unavailable to a user-defined one. Suppressing a
class of unwanted match MUST NOT require a code change, and MUST NOT require
rewriting a group's patterns.

Each exclusion SHALL be validated when the configuration is validated, before any
repository is acquired. An exclusion that is not a usable expression SHALL fail
validation and the error SHALL name the offending field, on the same terms as an
invalid pattern.

A group that declares only exclusions and no patterns SHALL continue to be
rejected, as a group that can never match already is: exclusions narrow a
group's matches and cannot produce any.

#### Scenario: Group declares a match-text exclusion

- **WHEN** a search-group is configured with an expression excluding a class of matched text
- **THEN** configuration validation succeeds
- **AND** the scan records no finding for text that expression matches

#### Scenario: Invalid exclusion expression

- **WHEN** a match-text exclusion is not a valid expression
- **THEN** configuration validation fails before any repository is acquired
- **AND** the error names the offending field

#### Scenario: Exclusions added to a seeded group

- **WHEN** the configuration adds a match-text exclusion to a seeded search-group
- **THEN** it takes effect exactly as it would on a user-defined group

#### Scenario: Group with exclusions but no patterns

- **WHEN** a search-group is configured with match-text exclusions and neither patterns nor colours
- **THEN** configuration validation fails and names the offending field
