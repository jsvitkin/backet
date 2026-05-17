# rules-ingestion Specification

## Purpose
TBD - created by archiving change add-rules-pdf-ingestion. Update Purpose after archive.
## Requirements
### Requirement: Rulebooks MUST be ingestible from local PDF paths

The system MUST ingest owned rulebooks from user-provided local PDF paths without requiring the user to manually pre-chunk or pre-convert them.

#### Scenario: Ingest a local PDF

- **WHEN** a user invokes rules ingestion with a path to a local PDF
- **THEN** the system MUST read that PDF from the local machine and begin a local ingestion pipeline

### Requirement: Source PDFs MUST remain external to the vault

The system MUST store ingested rule data in per-vault state while leaving the original PDF files outside the vault.

#### Scenario: Store ingested rule data

- **WHEN** a PDF is ingested successfully
- **THEN** the system MUST store the resulting chunks and metadata under `.backet/` without copying the source PDF into the vault

### Requirement: Rules ingestion MUST remain local

The system MUST keep extraction, OCR, chunking, and any embedding work local to the user's machine.

#### Scenario: Process a rulebook locally

- **WHEN** rulebook ingestion is running
- **THEN** the system MUST process the rulebook locally instead of sending PDF contents to a remote service

### Requirement: Rules ingestion MUST support OCR fallback

The system MUST support a local OCR fallback path when direct text extraction fails or yields insufficient output.

#### Scenario: Fall back to OCR

- **WHEN** direct text extraction from a rulebook PDF fails or is judged insufficient
- **THEN** the system MUST fall back to a local OCR path for the affected scope

### Requirement: Ingested chunks MUST include source metadata

The system MUST attach consistent source metadata to ingested rule chunks.

#### Scenario: Persist rule chunk metadata

- **WHEN** a rule chunk is stored after ingestion
- **THEN** the system MUST record the source book and source location metadata needed for later retrieval and precedence handling

### Requirement: Ingested chunks MUST include RAG-ready structure
The system MUST derive and persist rebuildable metadata needed by RAG v2 retrieval.

#### Scenario: Persist heading structure
- **WHEN** a rule chunk is stored or reindexed
- **THEN** the system MUST record the best available heading path, inferred section path, or section label needed to distinguish rules text from surrounding page noise

#### Scenario: Persist entity and alias metadata
- **WHEN** a rule chunk is stored or reindexed
- **THEN** the system MUST record rebuildable metadata for detected canonical aliases, scope tags, and whether each match came from heading text or body text

#### Scenario: Persist evidence cues
- **WHEN** a rule chunk is stored or reindexed
- **THEN** the system MUST record rebuildable evidence cues such as definition, system text, cost, dice pool, duration, prerequisite, targeting, advancement, consequence, example, lore, table of contents, index, or character sheet when detected

### Requirement: RAG metadata MUST be rebuildable
The system MUST be able to refresh RAG v2 retrieval metadata without requiring source PDFs when stored chunk text is available.

#### Scenario: Rebuild metadata from stored chunks
- **WHEN** an existing rules store has chunk text but lacks current RAG metadata
- **THEN** the rules indexing command MUST rebuild RAG metadata from stored chunks

#### Scenario: Metadata is stale
- **WHEN** stored RAG metadata no longer matches the chunk content hash or metadata schema version
- **THEN** audit or indexing diagnostics MUST identify the stale metadata and provide a refresh path

### Requirement: Reindex without source PDFs
The system SHALL refresh retrieval metadata and semantic indexes from stored rules database text without requiring source PDFs.

#### Scenario: Metadata schema changes
- **WHEN** retrieval metadata schema changes and stored chunk text is present
- **THEN** `backet rules index --full` refreshes metadata and reports that source PDFs were not needed

### Requirement: Reingest recommendation
The system SHALL recommend reingestion only when stored text, chunk structure, or source linkage is insufficient for reliable retrieval.

#### Scenario: Stored chunks are usable
- **WHEN** stored chunks have readable text but stale metadata
- **THEN** the system recommends reindexing instead of reingestion

#### Scenario: Stored chunks are unusable
- **WHEN** a book has many empty, art-heavy, or structurally broken chunks that cannot be repaired from stored text
- **THEN** the system reports the book as a reingest candidate with the required source PDF status

### Requirement: Chunk metadata quality
Rules ingestion and reindexing SHALL classify chunks by section kind, heading path, aliases, entity locations, evidence cues, and retrieval flags.

#### Scenario: Sheet page detected
- **WHEN** a chunk is a character sheet, table of contents, index, or page furniture
- **THEN** it is flagged so mechanical answer retrieval can demote or reject it

### Requirement: Section-aware rule blocks
Rules ingestion SHALL derive and persist section-aware rule blocks from extracted rulebook text.

#### Scenario: Rule block stored
- **WHEN** a rulebook page contains a named mechanic, discipline power, ritual, table, or rules subsection
- **THEN** ingestion stores a rule block with stable block ID, book metadata, source page range, heading path, block kind, clean text, and extraction quality metadata

#### Scenario: Page furniture excluded from block text
- **WHEN** repeated book headers, page numbers, chapter running heads, or decorative page furniture surround a rule block
- **THEN** the stored clean text excludes or flags that furniture so answer retrieval can center on the rule text

#### Scenario: Compatibility fields retained
- **WHEN** existing rules query callers request source metadata
- **THEN** the system continues to provide compatible book, page, section label, excerpt, and source type fields derived from the structured block

### Requirement: Structured tables and lists
Rules ingestion SHALL preserve rule-relevant table and list structure in block metadata and clean text.

#### Scenario: Trait cost table ingested
- **WHEN** a rulebook page contains a trait-cost or similar rule table
- **THEN** ingestion preserves row labels, values, and table context sufficiently for retrieval and answer synthesis to identify the applicable cost

#### Scenario: Discipline power stat block ingested
- **WHEN** a discipline power contains cost, dice pool, system, duration, prerequisite, or amalgam fields
- **THEN** ingestion keeps those labels associated with the named power block

### Requirement: Structure metadata rebuild
Rules indexing SHALL rebuild rule-block structure metadata from stored text when source PDFs are unavailable and stored text is sufficient.

#### Scenario: Stored text is sufficient
- **WHEN** a rules store has readable chunk text but stale or missing rule-block metadata
- **THEN** `backet rules index --full` rebuilds structure metadata without requiring the source PDF

#### Scenario: Stored text is insufficient
- **WHEN** stored text is empty, art-heavy, severely OCR-corrupted, or lacks source linkage needed to create reliable blocks
- **THEN** the indexing command reports the book as a reingest candidate rather than silently producing low-confidence blocks

### Requirement: Block schema versioning
Rules ingestion SHALL version rule-block metadata separately from source extraction so later retrieval changes can detect stale structure.

#### Scenario: Metadata schema changes
- **WHEN** the rule-block schema version changes
- **THEN** audit and indexing diagnostics identify stale blocks and provide the command needed to refresh them

### Requirement: Rules ingestion MUST derive rule units
Rules ingestion MUST derive or refresh structured rule units as rebuildable per-vault state after chunks and RAG metadata are available.

#### Scenario: Ingested book creates units
- **WHEN** a user ingests a rulebook successfully
- **THEN** the system MUST persist rule units linked to the resulting chunks and source metadata under `.backet/rules/`

#### Scenario: Ingestion output remains concise
- **WHEN** rules ingestion derives rule units in human-readable mode
- **THEN** the terminal output MUST summarize rule-unit counts and warnings without printing raw JSON, raw Python structures, full source passages, or source PDFs

### Requirement: Rules indexing MUST refresh stale rule units
Rules indexing MUST detect and refresh missing or stale rule units when stored chunk text, metadata schema, or rule-unit schema versions change.

#### Scenario: Stale unit schema
- **WHEN** existing rule units use an older schema version
- **THEN** the rules indexing command MUST refresh them or report why they cannot be refreshed

#### Scenario: Chunk-only legacy store
- **WHEN** a vault has stored rules chunks but no rule units
- **THEN** the rules indexing command MUST create rule units from stored chunks where sufficient

### Requirement: Rule-unit derivation MUST keep source PDFs external
Rule-unit derivation MUST NOT copy source PDFs into the vault or repository.

#### Scenario: Rule-unit rebuild requires original PDF
- **WHEN** a rule-unit refresh cannot proceed because stored chunks are insufficient and the original PDF is required
- **THEN** the system MUST report the missing source requirement without copying or committing the PDF

