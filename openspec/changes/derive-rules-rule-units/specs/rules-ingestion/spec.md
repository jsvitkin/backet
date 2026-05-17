## ADDED Requirements

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
