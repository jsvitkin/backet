## ADDED Requirements

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
