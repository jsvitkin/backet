## ADDED Requirements

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
