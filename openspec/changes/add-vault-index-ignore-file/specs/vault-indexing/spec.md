## ADDED Requirements

### Requirement: Vault indexing MUST honor index ignore policy

The system MUST apply a user-editable vault index ignore policy before indexing Markdown notes as canonical vault content.

#### Scenario: Ignore configured Markdown paths

- **WHEN** a user runs a vault indexing command in an initialized vault that contains `.backetignore`
- **THEN** the system MUST exclude Markdown files matched by `.backetignore` before parsing, chunking, embedding, or storing them

#### Scenario: Preserve built-in safety exclusions

- **WHEN** `.backetignore` is missing or edited to include Backet-owned state
- **THEN** the system MUST still exclude `.backet/` from the indexed vault corpus

#### Scenario: Remove newly ignored indexed notes

- **WHEN** a Markdown note was previously indexed and later becomes matched by `.backetignore`
- **THEN** the next index refresh MUST remove that note and its chunks from durable index state

#### Scenario: Continue when index ignore policy is missing

- **WHEN** a bootstrapped vault does not contain `.backetignore`
- **THEN** the system MUST continue indexing with built-in safety exclusions and surface that the optional index ignore policy file is missing

### Requirement: Context retrieval MUST exclude ignored vault content

The system MUST assemble context bundles only from Markdown notes that are part of the effective indexed vault corpus after ignore policy filtering.

#### Scenario: Query ignores excluded notes

- **WHEN** a user or agent requests context with a query that matches an ignored Markdown file
- **THEN** the system MUST NOT return sources from that ignored file

#### Scenario: Memory rebuild uses filtered corpus

- **WHEN** a user rebuilds derived memory after indexing with `.backetignore`
- **THEN** the system MUST derive memory from indexed, non-ignored notes rather than from all Markdown files in the vault
