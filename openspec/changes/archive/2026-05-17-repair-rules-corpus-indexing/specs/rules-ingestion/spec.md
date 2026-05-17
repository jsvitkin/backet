## ADDED Requirements

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

