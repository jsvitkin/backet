## ADDED Requirements

### Requirement: Vault indexing MUST operate on Markdown notes

The system MUST index Markdown notes from an initialized vault into per-vault state without assuming that PDFs or other binary attachments are part of the vault corpus.

#### Scenario: Index a Markdown vault

- **WHEN** a user runs a vault indexing command in an initialized vault
- **THEN** the system MUST parse Markdown notes and store indexable note chunks plus source metadata in `.backet/`

#### Scenario: Ignore non-Markdown vault files

- **WHEN** the vault contains non-Markdown files that are not part of the supported corpus
- **THEN** the system MUST leave them outside the Markdown indexing pipeline

### Requirement: Vault indexing MUST remain local

The system MUST generate embeddings and other index artifacts locally for vault content.

#### Scenario: Build local embeddings

- **WHEN** the indexing pipeline creates embeddings for vault note chunks
- **THEN** the system MUST perform that embedding work locally instead of sending vault content to a remote embedding service

### Requirement: Vault indexing MUST detect stale state after external edits

The system MUST recognize when canonical note content changed outside `backet` and guide the user or agent toward refresh behavior.

#### Scenario: Detect stale indexed state

- **WHEN** notes in the vault are modified outside `backet`
- **THEN** the next relevant `backet` command MUST detect that indexed state is stale before relying on it

#### Scenario: Recover from stale indexed state

- **WHEN** indexed state is stale
- **THEN** the system MUST offer or perform an appropriate refresh path instead of silently using outdated results

### Requirement: Durable index state MUST remain portable

The system MUST store durable index state in a form that can be committed with the vault, while keeping machine-specific scratch state rebuildable.

#### Scenario: Open a committed vault on another machine

- **WHEN** a user opens a vault with committed `.backet/` state on another machine
- **THEN** the system MUST use the durable committed state where possible and clearly identify any rebuildable local artifacts it needs to recreate
