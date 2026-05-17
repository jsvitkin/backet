## ADDED Requirements

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

