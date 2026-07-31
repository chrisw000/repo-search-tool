## ADDED Requirements

### Requirement: Configurable minimum candidate image size

The configuration SHALL expose the minimum candidate image size as a tunable
value with a documented default, governing which images are eligible for
similarity assessment. Raising it SHALL rule out more images; setting it to zero
SHALL assess every image whatever its size, which is how a run reproduces the
behaviour of a system without a minimum.

The configuration SHALL also expose a set of path patterns exempt from the
minimum, so that a class of legitimately small brand asset survives any minimum
chosen. These patterns SHALL be seeded with the favicon family and SHALL be
editable and removable by configuration like any other seeded value: raising the
minimum MUST NOT require a code change to keep favicons assessable, and clearing
the exemptions MUST NOT require one either.

Both values SHALL be validated before any repository is acquired. A minimum that
is not a non-negative integer SHALL fail validation naming the offending field,
and a value the configuration format resolves to a boolean SHALL be rejected
rather than admitted as a number. Exemption patterns SHALL be validated as
strings on the same terms as every other string-valued position.

The minimum actually in force SHALL be recorded in reporting, as the similarity
threshold already is, because a report read without it cannot be compared with
one taken under a different minimum.

#### Scenario: Minimum not specified

- **WHEN** the configuration does not specify a minimum candidate image size
- **THEN** the documented default is used
- **AND** the value used is recorded in reporting

#### Scenario: Minimum raised

- **WHEN** the minimum is raised and the scan is re-run over the same content
- **THEN** the set of images assessed is a subset of those assessed at the lower minimum

#### Scenario: Minimum disabled by configuration

- **WHEN** the configuration sets the minimum to zero
- **THEN** every image is assessed whatever its size

#### Scenario: Minimum given a value that is not a non-negative integer

- **WHEN** the minimum is given a negative value, a non-integer, or a boolean
- **THEN** configuration validation fails and names the offending field

#### Scenario: Favicons exempt without customisation

- **WHEN** a scan runs against a seeded configuration and the minimum is raised above a favicon's size
- **THEN** favicons are still assessed
- **AND** no code change was required to keep them assessable

#### Scenario: Exemptions replaced by configuration

- **WHEN** the configuration supplies its own exemption patterns
- **THEN** those patterns govern which paths are exempt from the minimum
- **AND** an exemption set given as empty exempts nothing
