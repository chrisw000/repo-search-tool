## ADDED Requirements

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
