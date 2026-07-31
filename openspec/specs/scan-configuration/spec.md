# scan-configuration Specification

## Purpose
Defines the single declarative configuration that drives a scan: which hosts and organisations to target, what text patterns to look for, which reference images to match against, and how tightly to match. Configuration is the extension point — new classes of brand reference are added by editing config, not code.

## Requirements

### Requirement: Single declarative configuration source

The system SHALL take its scan definition from one declarative configuration file. The configuration SHALL be validated before any repository is acquired. When validation fails, the system SHALL abort and identify the offending field by name.

#### Scenario: Invalid configuration

- **WHEN** the configuration is missing a required field or contains an invalid value
- **THEN** the system aborts before acquiring any repository
- **AND** the error names the offending field

#### Scenario: Valid configuration

- **WHEN** the configuration passes validation
- **THEN** the system proceeds to the authentication preflight

### Requirement: Numeric scalars admitted in string-valued configuration

Wherever the configuration expects a string, the system SHALL accept a value
written as a plain numeric scalar and treat it as a string. This applies to every
such position uniformly — brand vocabulary, search-group patterns and file globs,
scope globs and directories, disabled-group names, named repositories, and
reference-image labels — because a seeded search-group is an ordinary group and
MUST NOT enjoy admission rules unavailable to a user-defined one.

The string used SHALL be the value's source text exactly as written in the
configuration, not a re-rendering of a parsed numeric value. Leading zeros SHALL
be preserved, and a numeral that the configuration format would otherwise
reinterpret under a non-decimal reading SHALL still be searched for as written.
Silently searching for a different number than the one configured would report a
repository as clean when it is not, which is forbidden.

A value that is not a numeric scalar — a mapping, a nested list, an empty or null
entry, or a scalar the format resolves to a boolean — SHALL continue to be
rejected where a string was expected, and the error SHALL name the offending
field. An empty entry in particular MUST NOT be admitted as an empty pattern,
which would match every file scanned.

#### Scenario: Company number written as a bare numeral

- **WHEN** the configuration gives a legal string as an unquoted eight-digit
  numeral
- **THEN** configuration validation succeeds
- **AND** the legal-string search-group searches for that numeral as written

#### Scenario: Numeral whose digits invite a non-decimal reading

- **WHEN** the configuration gives a string-valued entry as an unquoted numeral
  with a leading zero whose remaining digits would also be valid under a
  non-decimal reading
- **THEN** the pattern searched for is the numeral exactly as it appears in the
  configuration file, including its leading zero
- **AND** the pattern searched for is not the decimal rendering of any alternative
  interpretation of those digits

#### Scenario: Numeric scalar in a non-legal string position

- **WHEN** an unquoted numeral appears in a brand name, a user-defined
  search-group's patterns, a file glob, or a named repository
- **THEN** it is admitted on the same terms as one appearing in the legal strings

#### Scenario: Quoted value unaffected

- **WHEN** a string-valued entry is written quoted
- **THEN** validation and the resulting pattern are unchanged from before this
  requirement existed

#### Scenario: Non-scalar where a string was expected

- **WHEN** a mapping or a nested list appears in a position expecting a string
- **THEN** configuration validation fails
- **AND** the error names the offending field

#### Scenario: Empty entry where a string was expected

- **WHEN** a list entry in a string-valued position is empty or null
- **THEN** configuration validation fails and names the offending field
- **AND** no pattern that would match every scanned file is produced

### Requirement: Typed configuration fields remain strictly typed

Admitting numeric scalars in string positions MUST NOT weaken validation of fields
that are genuinely typed. Fields specified as an integer SHALL still require an
integer, fields specified as a boolean SHALL still require a boolean, and
value-format validation that already applies to a string field SHALL continue to
apply to a value admitted by coercion.

#### Scenario: Integer field given a non-integer

- **WHEN** an integer-valued field such as the similarity threshold or the maximum
  file size is given a value that is not a valid integer for that field
- **THEN** configuration validation fails and names the offending field

#### Scenario: Boolean field given a non-boolean

- **WHEN** a boolean-valued field is given a value that is not a boolean
- **THEN** configuration validation fails and names the offending field

#### Scenario: Coerced value still subject to its field's format rules

- **WHEN** a numeric scalar is admitted into a field whose values must match a
  required format, such as a brand colour
- **THEN** it is checked against that format like any other string
- **AND** validation fails naming the offending field if it does not match

### Requirement: Named, extensible search-groups

Text search SHALL be expressed as named search-groups rather than fixed built-in categories. Each search-group SHALL carry its own set of patterns, its own file-scope include and exclude globs, and its own severity.

Adding, removing, or altering a search-group SHALL require only a configuration change. The system MUST NOT require a code change to introduce a new search-group.

#### Scenario: A new search-group is added by configuration

- **WHEN** a new named search-group with its own patterns, scope, and severity is added to the configuration
- **THEN** the scan executes that group alongside the existing ones
- **AND** its matches are attributed to that group name with that group's severity

#### Scenario: A search-group restricts its own file scope

- **WHEN** a search-group defines include globs narrower than the global scope
- **THEN** that group is evaluated only against files matching its own globs
- **AND** other groups are unaffected

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

### Requirement: Labelled reference-image set

The configuration SHALL identify a folder of reference images, and each reference image SHALL carry a label identifying the brand layout it represents. Labels SHALL be reportable, so that a match can name which reference it matched.

#### Scenario: Reference image matched

- **WHEN** an image in a repository matches a reference image
- **THEN** the finding names that reference image's label

#### Scenario: Reference image lacks a label

- **WHEN** a reference image has no resolvable label
- **THEN** configuration validation fails and names the offending reference image

### Requirement: Tunable similarity threshold

The configuration SHALL expose the image-similarity threshold as a tunable value with a documented default. Lowering it SHALL make matching stricter; raising it SHALL make matching more permissive.

#### Scenario: Threshold tightened

- **WHEN** the threshold is lowered and the scan is re-run over the same content
- **THEN** the set of image matches reported is a subset of those reported at the higher threshold

#### Scenario: Threshold not specified

- **WHEN** the configuration does not specify a threshold
- **THEN** the documented default is used
- **AND** the value used is recorded in reporting

### Requirement: File-scope defaults

The configuration SHALL provide global file-scope defaults. Dependency directories SHALL be excluded by default. Build-output directories MUST NOT be excluded by default, because deployed brand assets frequently exist only in build output and excluding them would cause silent misses.

All scope defaults SHALL be overridable by configuration.

#### Scenario: Dependency directory encountered

- **WHEN** a repository contains a dependency directory and no override is configured
- **THEN** files inside it are not scanned

#### Scenario: Build-output directory encountered

- **WHEN** a repository contains a build-output directory and no override is configured
- **THEN** files inside it are scanned
- **AND** matches within it are reported

#### Scenario: Scope default overridden

- **WHEN** the configuration overrides a scope default
- **THEN** the override governs which files are scanned
