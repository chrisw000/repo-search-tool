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

### Requirement: Default search-groups seeded

The configuration SHALL be seeded with default search-groups covering brand names, font names, font references, legacy domains, brand colours, and legal or trademark strings. These defaults SHALL be editable and removable like any other group.

#### Scenario: Default groups present without customisation

- **WHEN** a scan runs against a seeded configuration with no user-added groups
- **THEN** the brand-name, font-name, font-reference, legacy-domain, brand-colour, and legal-string groups are all executed

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
