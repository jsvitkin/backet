# hybrid-rules-retrieval Specification

## Purpose
TBD - created by archiving change add-hybrid-rules-retrieval. Update Purpose after archive.
## Requirements
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

### Requirement: Rules retrieval MUST produce a staged evidence packet
The system MUST retrieve rules through a staged RAG pipeline that separates candidate generation, reranking, evidence gating, and final source selection.

#### Scenario: RAG v2 query returns evidence packet
- **WHEN** a rules query is executed with RAG v2 retrieval available
- **THEN** the machine-readable response MUST include an evidence packet containing selected evidence, fallback context, rejected high-scoring candidates, evidence status, candidate counts, and retrieval diagnostics

#### Scenario: Existing result fields retained
- **WHEN** RAG v2 retrieval returns results during the transition period
- **THEN** the response MUST continue to expose primary and fallback result fields or a documented compatibility equivalent for existing callers

### Requirement: Candidate generation MUST use planned retrieval channels
The system MUST gather candidates from multiple bounded retrieval channels derived from the query plan.

#### Scenario: Planned exact candidates
- **WHEN** a query plan contains canonical terms and aliases
- **THEN** candidate generation MUST run exact or phrase retrieval for those planned terms

#### Scenario: Semantic candidates
- **WHEN** compatible semantic embeddings are available
- **THEN** candidate generation MUST include semantic candidates and report the embedding backend and model used

#### Scenario: Raw fallback candidates
- **WHEN** planned retrieval is available
- **THEN** candidate generation MAY include raw query fallback candidates but MUST mark them separately from planned candidates in diagnostics

### Requirement: RAG v2 MUST rerank candidates before source selection
The system MUST rerank candidates against the query plan before selecting answer sources.

#### Scenario: Intent-aware reranking
- **WHEN** the query plan marks advancement intent
- **THEN** reranking MUST prefer chunks with advancement, acquisition, prerequisite, or learning-rule evidence over chunks that merely mention the named discipline

#### Scenario: Targeting-aware reranking
- **WHEN** the query plan marks targeting or applicability intent
- **THEN** reranking MUST prefer chunks with system text, target restrictions, or applicability evidence over lore-only mentions

#### Scenario: Definition-aware reranking
- **WHEN** the query plan marks definition intent
- **THEN** reranking MUST prefer definition or explanatory chunks over incidental mentions or activation costs

### Requirement: RAG v2 MUST gate answerability
The system MUST classify whether selected evidence can answer the planned question.

#### Scenario: Evidence is sufficient
- **WHEN** selected chunks satisfy the required evidence hints in the query plan
- **THEN** the evidence packet MUST mark the query as answerable

#### Scenario: Evidence is only a mention
- **WHEN** selected chunks mention the requested entity but do not satisfy the required evidence hints
- **THEN** the evidence packet MUST mark the query as insufficient and include the missing evidence type

#### Scenario: Comparable sources conflict
- **WHEN** selected answerable chunks from comparable authoritative sources conflict or have comparable precedence
- **THEN** the evidence packet MUST mark the query as ambiguous or conflicting rather than silently selecting one source

### Requirement: Semantic quality MUST be explicit
The system MUST report whether semantic retrieval used a production-quality embedding backend or a degraded fallback.

#### Scenario: Hash backend used
- **WHEN** semantic retrieval uses the hash embedding backend
- **THEN** diagnostics MUST report degraded semantic quality and MUST NOT present the result as equivalent to sentence-level semantic retrieval

#### Scenario: Semantic backend unavailable
- **WHEN** a compatible semantic backend is unavailable
- **THEN** retrieval MUST fall back to exact and metadata-aware channels and report that semantic retrieval was unavailable

### Requirement: Anchored exact retrieval
Hybrid rules retrieval SHALL run anchored exact channels that require query entities and intent evidence to co-occur before using broad fallback channels.

#### Scenario: Anchored query succeeds
- **WHEN** a query has a known entity and an intent such as targeting, cost, advancement, or consequence
- **THEN** anchored channels prefer chunks where the entity and intent evidence occur in the same chunk or bounded neighbor window

#### Scenario: Broad OR result is demoted
- **WHEN** a chunk matches only one side of the query, such as only the clan name or only a generic target word
- **THEN** that chunk is demoted or rejected as a broad fallback result

### Requirement: Candidate rejection reasons
Hybrid rules retrieval SHALL include structured rejection reasons for candidates excluded from selected evidence.

#### Scenario: Candidate lacks target entity
- **WHEN** a candidate has system text but lacks the requested entity or accepted alias
- **THEN** the candidate is rejected with `missing_entity_anchor`

#### Scenario: Candidate is low-quality section
- **WHEN** a candidate comes from a character sheet, table of contents, index, art-heavy, or lore-only section for a mechanical query
- **THEN** the candidate is rejected or heavily demoted with a low-quality-section reason

### Requirement: Bounded neighbor expansion
Hybrid rules retrieval SHALL support bounded neighbor expansion around a strong anchor chunk when the answer evidence spans adjacent chunks.

#### Scenario: System text follows heading chunk
- **WHEN** a chunk contains the requested power heading and an adjacent chunk contains its system text
- **THEN** retrieval may include the adjacent chunk as selected evidence if the combined window satisfies answerability

### Requirement: Clean source windows
Hybrid rules retrieval SHALL provide answer windows centered on matched anchors and evidence cues rather than raw page starts.

#### Scenario: Source page starts with page furniture
- **WHEN** a chunk begins with repeated book headers or page numbers
- **THEN** the retrieval result excerpt starts near the matched rule text when such a window is available

### Requirement: Metadata freshness gating
Hybrid rules retrieval SHALL report stale or missing retrieval metadata that may affect answer quality.

#### Scenario: Metadata is stale
- **WHEN** a query runs against chunks whose retrieval metadata schema is stale
- **THEN** JSON output reports the stale metadata count and suggests reindexing

