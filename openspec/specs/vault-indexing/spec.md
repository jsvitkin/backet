# vault-indexing Specification

## Purpose
TBD - created by archiving change add-vault-index-ignore-file. Update Purpose after archive.
## Requirements
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

### Requirement: Bot export MUST build access-scoped vault indexes
The system MUST be able to build vault indexes for bot access scopes using the effective vault access policy.

#### Scenario: Build player index
- **WHEN** a user exports a bot bundle for a vault with player-visible notes
- **THEN** the system MUST build a player vault index containing only notes eligible for player bot retrieval

#### Scenario: Build Storyteller index
- **WHEN** a user exports a bot bundle for a vault with Storyteller-eligible notes
- **THEN** the system MUST build a Storyteller vault index containing the broader Storyteller-authorized corpus while still excluding bot-excluded and built-in ignored content

#### Scenario: No player-visible notes
- **WHEN** the effective policy contains no player-visible notes
- **THEN** bot export MUST either create an empty player index with a warning or fail according to the configured export policy

### Requirement: Bot indexes MUST preserve existing retrieval guarantees
Access-scoped bot indexes MUST preserve bounded context retrieval, exact search, semantic ranking, metadata filters, hierarchy-aware expansion, and deterministic source metadata within each permitted corpus.

#### Scenario: Player semantic query
- **WHEN** a player command queries the player vault index with conceptual language
- **THEN** the system MUST retrieve bounded context only from player-visible indexed chunks using the configured exact and semantic retrieval behavior

#### Scenario: Storyteller exact lookup
- **WHEN** a Storyteller command queries the Storyteller vault index for an exact named entity
- **THEN** the system MUST prioritize exact and metadata-aware matches within the Storyteller-authorized corpus

#### Scenario: Source metadata returned
- **WHEN** bot retrieval returns vault sources
- **THEN** each source MUST include enough metadata for answer citation, including relative path, title, heading path, excerpt, score, and match reasons

### Requirement: Unauthorized content MUST never appear in lower-tier bot retrieval
The system MUST prevent lower-tier bot indexes and retrieval outputs from containing unauthorized notes, chunks, excerpts, titles, headings, or metadata.

#### Scenario: Hidden plotline matches player query
- **WHEN** a player query matches text from a Storyteller-only plotline
- **THEN** player bot retrieval MUST NOT return that plotline or any metadata revealing its presence

#### Scenario: Storyteller-only NPC shares a name with public canon
- **WHEN** a player query matches both a public canon note and a hidden NPC note
- **THEN** player bot retrieval MUST return only permitted public sources and MUST NOT include hidden NPC excerpts or hidden-note titles

#### Scenario: Bot-excluded note matches any query
- **WHEN** a note is excluded from bot export
- **THEN** no bot access scope MUST return that note even if normal local `backet context` would retrieve it

### Requirement: Visibility metadata changes MUST refresh bot index eligibility
The system MUST detect when note visibility metadata or command-topic metadata changes require bot indexes to be rebuilt.

#### Scenario: Note becomes player-visible
- **WHEN** a note's visibility changes from Storyteller-only to player-visible
- **THEN** the next bot export MUST include the note in the player index and update the bundle manifest policy hash

#### Scenario: Note becomes hidden
- **WHEN** a note's visibility changes from player-visible to Storyteller-only or bot-excluded
- **THEN** the next bot export MUST remove the note and its chunks from the player index

#### Scenario: Topic metadata changes without body changes
- **WHEN** note bot topic metadata changes but Markdown body content is unchanged
- **THEN** bot export MUST still rebuild or update access-scoped indexes affected by the metadata change

### Requirement: Bot indexes MUST be portable bundle artifacts
The system MUST write access-scoped indexes as portable artifacts that can be copied to the hosted bot runtime without the source vault.

#### Scenario: Export portable indexes
- **WHEN** bot export completes
- **THEN** the generated access-scoped index files MUST be usable by the bot runtime from the bundle path without needing the original Obsidian vault path

#### Scenario: Manifest records index files
- **WHEN** bot export writes access-scoped indexes
- **THEN** the bundle manifest MUST list each index file, access scope, note count, chunk count, content fingerprint, and embedding backend/model metadata

#### Scenario: Runtime index missing
- **WHEN** the bot runtime starts and a manifest-listed index file is missing
- **THEN** the runtime MUST fail closed for commands that require that index and report a diagnostic to Storyteller health checks

