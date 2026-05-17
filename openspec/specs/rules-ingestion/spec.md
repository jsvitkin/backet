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

