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

### Requirement: Vault initialization MUST bootstrap scoped `backet` state

The system MUST allow a user to initialize `backet` inside an existing Obsidian vault without assuming that the `backet` repository itself is the vault.

#### Scenario: Initialize a new vault

- **WHEN** a user runs `backet init` against an Obsidian vault
- **THEN** the system creates a `.backet/` directory with the durable files and folders required for future `backet` operations

#### Scenario: Re-run initialization on an already bootstrapped vault

- **WHEN** a user runs `backet init` in a vault that already contains `.backet/`
- **THEN** the system MUST detect the existing bootstrap state and guide the user instead of silently overwriting it

### Requirement: `backet` MUST manage scoped Git ignore behavior

The system MUST isolate its machine-specific scratch artifacts with `.backet/.gitignore` rather than depending on changes to the vault root `.gitignore`.

#### Scenario: Bootstrap ignore rules

- **WHEN** vault initialization creates `.backet/`
- **THEN** the system creates `.backet/.gitignore` entries for machine-specific or rebuildable artifacts

#### Scenario: Preserve durable vault state

- **WHEN** initialization writes durable per-vault state
- **THEN** that durable state MUST remain outside the ignored scratch locations so it can be committed with the vault

### Requirement: Missing local state MUST be recoverable

The system MUST detect missing rebuildable artifacts and provide a clear repair path on a new machine or after local cleanup.

#### Scenario: Reopen a vault on a machine missing local artifacts

- **WHEN** a user or agent invokes `backet` in a bootstrapped vault and rebuildable local artifacts are missing
- **THEN** the system MUST report what is missing and provide or invoke a recovery command instead of failing ambiguously

### Requirement: Automatic repair MUST stay within safe boundaries

The system MUST limit automatic repair behavior to deterministic rebuildable artifacts and MUST require explicit user action for repairs that may overwrite durable state or cross compatibility boundaries.

#### Scenario: Auto-fix a safe rebuildable artifact

- **WHEN** `backet doctor` encounters a missing or stale rebuildable local artifact with a deterministic repair path
- **THEN** the system MAY repair it automatically when the user requests automatic repair

#### Scenario: Refuse an unsafe automatic repair

- **WHEN** `backet doctor` encounters a problem whose repair could overwrite durable state or alter compatibility-sensitive data
- **THEN** the system MUST stop short of automatic repair and explain the required manual action

