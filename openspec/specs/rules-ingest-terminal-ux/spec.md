# rules-ingest-terminal-ux Specification

## Purpose
Define the human-facing terminal visibility, progress, and completion reporting expected from rules ingestion commands.
## Requirements
### Requirement: Rules ingest MUST show live progress in human terminal output

The system MUST make `backet rules ingest` visibly active during long-running human-terminal runs, including before per-page extraction begins and while extraction, OCR, storage, indexing, and summary work is underway.

#### Scenario: Human ingest starts visibly before long-running work

- **WHEN** a user runs `backet rules ingest` without `--json` against a readable PDF
- **THEN** the command MUST emit human-readable start/status output before beginning long-running per-page extraction
- **AND** the output MUST identify the book, source PDF, selected page scope, and target rules store

#### Scenario: Human ingest reports page extraction progress

- **WHEN** a human `rules ingest` run is extracting pages from a multi-page rulebook
- **THEN** the command MUST show page-based progress that includes the current processed page count and total selected pages

#### Scenario: Human ingest reports OCR fallback activity

- **WHEN** a page requires OCR fallback during a human `rules ingest` run
- **THEN** the command MUST label the current activity as OCR fallback and continue showing overall extraction progress

#### Scenario: Human ingest reports non-page phases

- **WHEN** a human `rules ingest` run is performing storage, chunking, search indexing, or audit-summary work after page extraction
- **THEN** the command MUST show a visible phase label or progress indicator until the phase completes

#### Scenario: Interactive human ingest shows progress by default

- **WHEN** a user runs `backet rules ingest` without `--json` in an interactive terminal
- **THEN** progress MUST be visible by default without requiring a progress option

#### Scenario: Non-interactive human ingest prints plain phase lines

- **WHEN** a user runs `backet rules ingest` without `--json` in a non-interactive or redirected environment
- **THEN** the command MUST print plain human-readable phase/status lines during long-running work
- **AND** the output MUST avoid terminal control sequences that require an interactive TTY

### Requirement: Rules ingest MUST preserve deterministic JSON output

The system MUST keep progress and human-oriented status text separate from `--json` stdout output.

#### Scenario: JSON ingest remains parseable

- **WHEN** a user runs `backet --json rules ingest`
- **THEN** stdout MUST contain only the final deterministic JSON result or error payload
- **AND** human progress output MUST NOT be written to stdout

#### Scenario: JSON ingest retains complete diagnostic fields

- **WHEN** a JSON `rules ingest` run completes with OCR pages or suspect pages
- **THEN** the JSON result MUST retain the full machine-readable fields for OCR pages, suspect pages, processed pages, and chunk count

### Requirement: Rules ingest MUST summarize completion output for humans
The system MUST present human completion output as a concise report rather than an unbounded dump of raw data fields, including a bounded summary of generated rule scope assertions when scope generation runs.

#### Scenario: Human ingest completion shows primary outcome first
- **WHEN** a human `rules ingest` run completes successfully
- **THEN** the completion output MUST show the book identity, processed page count, stored chunk count, rules store location, and source PDF location before lower-priority diagnostics

#### Scenario: Human ingest completion summarizes long page lists
- **WHEN** a human `rules ingest` result contains long lists of OCR pages or suspect pages
- **THEN** the completion output MUST show counts and a bounded preview rather than printing the full unbounded lists by default

#### Scenario: Human ingest completion omits empty diagnostics
- **WHEN** a human `rules ingest` result has no values for optional diagnostics such as scope tags, OCR pages, or suspect pages
- **THEN** the completion output MUST omit those empty diagnostics instead of printing empty arrays or empty sections

#### Scenario: Human ingest completion summarizes generated scopes
- **WHEN** a human `rules ingest` run generates rule scope assertions
- **THEN** the completion output MUST summarize source scope, applied assertion count, suggested assertion count, and review-needed count
- **AND** the output MUST show a bounded preview of notable scope spans rather than printing the full manifest by default

#### Scenario: Human ingest completion identifies scope review path
- **WHEN** generated scope assertions include suggested or review-needed spans
- **THEN** the completion output MUST include the command or next action for inspecting those scope assertions

### Requirement: Rules ingest MUST label non-normal outcomes in human terms

The system MUST use human-friendly labels for ingestion outcomes that need interpretation or follow-up.

#### Scenario: OCR pages are labeled as OCR-required pages

- **WHEN** a human `rules ingest` result includes pages processed through OCR fallback
- **THEN** the completion output MUST label them as pages that required OCR rather than exposing only an implementation field name

#### Scenario: Suspect pages are labeled as pages needing review

- **WHEN** a human `rules ingest` result includes suspect pages
- **THEN** the completion output MUST label them as pages needing review or low-confidence pages rather than exposing only an implementation field name

#### Scenario: Review guidance is shown for suspect pages

- **WHEN** a human `rules ingest` result includes suspect pages
- **THEN** the completion output MUST include a follow-up command or instruction for auditing the ingested book
