## MODIFIED Requirements

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
