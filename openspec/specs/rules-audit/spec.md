# rules-audit Specification

## Purpose
TBD - created by archiving change add-rules-pdf-ingestion. Update Purpose after archive.
## Requirements
### Requirement: Rules ingestion MUST track confidence for audit

The system MUST retain enough ingestion-quality information to identify suspect OCR or chunking output.

#### Scenario: Record low-confidence spans

- **WHEN** the ingestion pipeline encounters pages or chunks with degraded extraction quality
- **THEN** the system MUST preserve confidence or quality indicators that can be surfaced later

### Requirement: The system MUST support rules audit reporting

The system MUST provide a way to inspect low-confidence or structurally suspect ingested rule data.

#### Scenario: Audit an ingested book

- **WHEN** a user runs a rules audit command
- **THEN** the system MUST report the suspect pages, chunks, or sections that may need review

### Requirement: The system MUST support targeted recovery

The system MUST allow repair or re-ingestion of a narrower scope than the full corpus.

#### Scenario: Reprocess a subset of a rulebook

- **WHEN** a user chooses a suspect book, section, page, or page range for repair
- **THEN** the system MUST support re-running extraction or OCR for that targeted scope without forcing a full-corpus re-ingest

### Requirement: Corpus health actions
Rules audit SHALL summarize corpus health actions as none, reindex, repair, or reingest.

#### Scenario: Full reindex needed
- **WHEN** metadata or semantic indexes are stale but source text is usable
- **THEN** audit human output recommends `backet rules index <vault> --full`

#### Scenario: Source repair needed
- **WHEN** a book requires OCR repair or reingestion
- **THEN** audit output identifies the book, stored source path or missing source fingerprint, and the safest next command

### Requirement: Human output is interpreted
Rules audit human output SHALL explain corpus health findings without dumping raw JSON dictionaries or internal payload keys.

#### Scenario: Corpus health has issues
- **WHEN** audit finds stale metadata and reingest candidates
- **THEN** human output groups them under concise headings with actionable commands

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

