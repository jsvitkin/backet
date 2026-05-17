## ADDED Requirements

### Requirement: Corpus structure audit
Rules audit SHALL report whether ingested rulebooks have reliable block structure for answer-quality retrieval.

#### Scenario: Structure health reported
- **WHEN** a user runs rules audit
- **THEN** the report includes counts for structured blocks, stale block metadata, page-furniture-heavy blocks, empty blocks, mixed-topic blocks, table/list blocks, and reingest candidates

#### Scenario: Reindex recommended
- **WHEN** stored text is readable but block metadata is missing or stale
- **THEN** audit recommends reindexing rather than source-PDF reingestion

#### Scenario: Reingestion recommended
- **WHEN** stored text is unusable or source linkage is too broken to derive reliable block structure
- **THEN** audit recommends reingestion and identifies the affected book without requiring the PDF path in normal output

### Requirement: Structure diagnostics in machine output
Rules audit SHALL expose structure health in deterministic machine-readable output.

#### Scenario: JSON audit requested
- **WHEN** a user runs rules audit with JSON output
- **THEN** the payload includes per-book structure health, stale schema counts, reindex eligibility, reingest recommendation, and bounded sample block IDs
