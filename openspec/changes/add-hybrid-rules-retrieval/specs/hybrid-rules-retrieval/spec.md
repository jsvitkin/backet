## ADDED Requirements

### Requirement: Rule chunks MUST support local semantic indexing

The system MUST be able to create and persist local embeddings for ingested rule chunks while keeping source PDFs external to the vault.

#### Scenario: Build semantic index during rules ingestion

- **WHEN** a user ingests a rulebook and a local embedding backend is available
- **THEN** the system MUST store embeddings for the resulting rule chunks in the per-vault rules store under `.backet/rules/`

#### Scenario: Rebuild embeddings for existing rules

- **WHEN** an existing ingested rule chunk lacks an embedding or its stored embedding content hash is stale
- **THEN** the system MUST provide a local rebuild path that refreshes the embedding without requiring the source PDF to be copied into the vault

### Requirement: Rules semantic indexing MUST expose a dedicated refresh command

The system MUST provide a dedicated rules indexing command for building and refreshing semantic rule index artifacts.

#### Scenario: Refresh rule embeddings

- **WHEN** a user or agent runs `backet rules index` for an initialized vault
- **THEN** the system MUST build or refresh missing and stale rule embeddings in the per-vault rules store

#### Scenario: Report semantic coverage

- **WHEN** a user or agent runs `backet rules index` in machine-readable mode
- **THEN** the system MUST report embedding backend, embedding model, indexed chunk count, missing count, stale count, and refreshed count

### Requirement: Rule embeddings MUST be stored in inspectable JSON form

The system MUST store rule chunk embeddings as JSON in the per-vault rules store for the first implementation.

#### Scenario: Persist rule embedding

- **WHEN** the system embeds a rule chunk
- **THEN** it MUST persist the vector in an inspectable JSON field together with backend, model, dimensions, and content hash metadata

### Requirement: Rules queries MUST use hybrid retrieval when semantic index is available

The system MUST combine exact full-text search and semantic vector retrieval when querying ingested rules with available embeddings.

#### Scenario: Query conceptual rule language

- **WHEN** a user queries for a conceptual authoring prompt that does not use exact rulebook vocabulary
- **THEN** the system MUST be able to retrieve semantically relevant rule chunks in addition to exact lexical matches

#### Scenario: Query exact rule terminology

- **WHEN** a user queries for exact rule terms, book terms, or named mechanics
- **THEN** the system MUST continue to prioritize exact and metadata-aware matches instead of relying only on semantic similarity

### Requirement: Rules queries MUST preserve source authority and precedence

Hybrid rules retrieval MUST preserve raw source chunk output, source metadata, core fallback behavior, supplement precedence, and ambiguity handling.

#### Scenario: Supplement match outranks core fallback

- **WHEN** exact or semantic retrieval finds both a core chunk and a scope-relevant supplement chunk for the same rules area
- **THEN** the system MUST prioritize the supplement-specific chunk while keeping the core chunk available as fallback context

#### Scenario: Comparable supplement matches remain ambiguous

- **WHEN** hybrid retrieval finds multiple comparable supplement-specific sources for the same rule area without a clear precedence decision
- **THEN** the system MUST surface an ambiguity error or ambiguity metadata rather than silently selecting one source

### Requirement: Rules ranking MUST account for extraction quality and non-answer sections

The system MUST use stored, rebuildable retrieval-quality metadata together with ingestion confidence and source metadata to reduce noisy rules results without deleting the underlying corpus.

#### Scenario: Store retrieval quality metadata

- **WHEN** a rule chunk is ingested, repaired, or reindexed
- **THEN** the system MUST derive and store rebuildable retrieval-quality metadata that can identify likely navigational, sheet, index, table-of-contents, art-heavy, very short, or suspect OCR chunks

#### Scenario: Low-confidence OCR competes with clean rule text

- **WHEN** a low-confidence OCR chunk and a clean direct-extraction chunk both match a rules query
- **THEN** the system MUST prefer the clean chunk unless the low-confidence chunk has stronger exact or semantic evidence

#### Scenario: Navigational pages match broad query terms

- **WHEN** table-of-contents, index, character-sheet, form, or art-heavy chunks match broad query terms
- **THEN** the system MUST downrank those chunks below substantive rule text when substantive rule text is available

### Requirement: Rules query output MUST expose retrieval diagnostics

The system MUST expose deterministic metadata about how a rules query was retrieved and ranked.

#### Scenario: Hybrid query returns results

- **WHEN** a rules query uses both exact and semantic retrieval
- **THEN** the machine-readable response MUST identify the retrieval mode, embedding backend/model, and match reasons for returned chunks

#### Scenario: Semantic retrieval is unavailable

- **WHEN** semantic embeddings are missing, stale, or the configured embedding backend is unavailable
- **THEN** the system MUST fall back to exact rules retrieval and report that semantic retrieval was not used

### Requirement: Rules semantic indexing MUST remain local

The system MUST keep rule embedding generation and semantic search local to the user's machine.

#### Scenario: Generate rule embeddings

- **WHEN** the system embeds rule chunks for indexing or repair
- **THEN** it MUST NOT send rulebook text, extracted chunks, or embeddings to a remote service
