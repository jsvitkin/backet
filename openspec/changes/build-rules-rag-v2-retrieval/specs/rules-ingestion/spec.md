## ADDED Requirements

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
