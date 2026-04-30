# vault-bootstrap Specification

## Purpose
TBD - created by archiving change add-vault-index-ignore-file. Update Purpose after archive.
## Requirements
### Requirement: Vault initialization MUST create index ignore policy

The system MUST create a root-level `.backetignore` file when initializing `backet` inside a vault so users can control which Markdown files become indexed canon.

#### Scenario: Initialize vault with default index ignore policy

- **WHEN** a user runs `backet init` against an uninitialized vault
- **THEN** the system MUST create `.backetignore` at the vault root with default patterns for Backet-owned state, common Obsidian/system folders, and common support-note folders such as `Templates/`, `Archive/`, and `Daily Notes/`

#### Scenario: Keep index policy separate from Git ignore policy

- **WHEN** vault initialization creates both `.backetignore` and `.backet/.gitignore`
- **THEN** `.backetignore` MUST control vault indexing and `.backet/.gitignore` MUST control Git ignore behavior for Backet-owned scratch state

### Requirement: Vault repair MUST restore missing index ignore policy safely

The system MUST detect a missing `.backetignore` file in a bootstrapped vault and provide a safe repair path that does not overwrite user policy.

#### Scenario: Report missing index ignore policy

- **WHEN** `backet doctor` inspects a bootstrapped vault without `.backetignore`
- **THEN** the system MUST report the missing index ignore policy as a safe-to-fix warning

#### Scenario: Restore missing index ignore policy

- **WHEN** `backet doctor --fix` inspects a bootstrapped vault without `.backetignore`
- **THEN** the system MUST create the default `.backetignore` file

#### Scenario: Preserve existing user-edited index ignore policy

- **WHEN** `backet doctor --fix` inspects a bootstrapped vault with an existing `.backetignore`
- **THEN** the system MUST NOT overwrite the existing file

