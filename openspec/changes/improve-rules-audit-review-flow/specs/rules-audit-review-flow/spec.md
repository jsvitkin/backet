## ADDED Requirements

### Requirement: Rules audit MUST present a human action summary

The system MUST render non-JSON `backet rules audit` output as a bounded human summary that separates automatic maintenance, human review items, notices, blocked repairs, and scope-related follow-up.

#### Scenario: Audit finds automatic maintenance work
- **WHEN** a user runs `backet rules audit` and ingested rule chunks have missing or stale semantic embeddings or retrieval metadata
- **THEN** the human output MUST identify the issue as automatic maintenance rather than page review
- **AND** the output MUST identify the affected book or corpus scope and the automatic repair action available

#### Scenario: Audit finds reviewable extraction issues
- **WHEN** a user runs `backet rules audit --book-id <book>` and the book has suspect pages or low-confidence OCR chunks that are not already resolved by a current review decision
- **THEN** the human output MUST summarize the count of reviewable pages and low-confidence chunks
- **AND** the output MUST show a bounded preview of review cards grouped by book and page
- **AND** the output MUST avoid dumping raw nested fields such as `suspect_pages`, `suspect_chunks`, or `semantic_index`

#### Scenario: Audit finds only notices
- **WHEN** audited pages only have informational OCR fallback, likely art/title/blank/index findings, or previously reviewed unchanged findings
- **THEN** the human output MUST label those items as notices or already reviewed rather than urgent work

#### Scenario: Audit has no actionable findings
- **WHEN** the audited rules corpus has no maintenance work, no unreviewed extraction issues, and no blocked source repairs
- **THEN** the human output MUST clearly state that the audited scope is healthy

### Requirement: Rules audit MUST report source PDF repair status

The system MUST include source PDF status in audit results so users know whether automatic page repair can rescan the original source.

#### Scenario: Stored source PDF is available
- **WHEN** a user audits a book whose stored PDF path exists and whose fingerprint matches the ingested fingerprint
- **THEN** the audit result MUST mark the source PDF as available for automatic repair

#### Scenario: Stored source PDF is missing
- **WHEN** a user audits a book whose stored PDF path no longer exists
- **THEN** the audit result MUST mark automatic OCR repair as blocked
- **AND** the human output MUST guide the user toward relinking the source PDF or re-ingesting the book

#### Scenario: Stored source PDF fingerprint differs
- **WHEN** a user audits a book whose stored PDF path exists but no longer matches the ingested fingerprint
- **THEN** the audit result MUST mark automatic OCR repair as blocked unless the user explicitly relinks or confirms the replacement source

### Requirement: The system MUST support durable audit review decisions

The system MUST let users resolve audit findings with explicit decisions and MUST persist those decisions in the per-vault rules store without modifying Obsidian canon notes.

#### Scenario: User accepts extracted text
- **WHEN** a user accepts a reviewable page or chunk as usable
- **THEN** the system MUST persist an accepted decision keyed to the finding target and current content hash
- **AND** future audits MUST not show the unchanged finding as urgent review work

#### Scenario: User ignores expected non-rules material
- **WHEN** a user marks a finding as ignored because it is expected art, title, blank, index, or otherwise non-actionable material
- **THEN** the system MUST persist an ignored decision keyed to the finding target and current content hash
- **AND** future audits MUST not show the unchanged finding as urgent review work
- **AND** the ignored decision MUST NOT by itself exclude affected chunks from rules retrieval

#### Scenario: User excludes useless extracted text from retrieval
- **WHEN** a user excludes a page or chunk from rules retrieval
- **THEN** the system MUST retain audit provenance for the source material
- **AND** the affected chunks MUST be ineligible for future `backet rules query` results
- **AND** future audits MUST show the unchanged finding as resolved or excluded rather than urgent review work

#### Scenario: Extracted content changes after review
- **WHEN** a previously reviewed page or chunk is repaired, replaced, or re-ingested and its content hash changes
- **THEN** the previous review decision MUST NOT suppress new audit findings for the changed content

### Requirement: The system MUST provide a guided review queue

The system MUST provide a human workflow for stepping through reviewable audit findings and choosing an available decision for each finding. Non-JSON `backet rules audit` MUST be the human-first entry point for this workflow, while JSON and explicit non-interactive options MUST serve agents, tests, and scripts.

#### Scenario: Human audit has reviewable findings
- **WHEN** a user runs non-JSON `backet rules audit` in an interactive terminal and the selected scope has reviewable findings
- **THEN** the system MUST summarize the audit status
- **AND** the system MUST guide the user toward the next review card without requiring an agent-style flag

#### Scenario: User reviews a flagged page
- **WHEN** a user reviews a pending page finding
- **THEN** the system MUST show one bounded review card at a time with book, page, finding reason, source status, extracted text preview, and available actions
- **AND** the available actions MUST include accept, ignore, exclude, retry, replace, and skip when applicable

#### Scenario: Agent resolves a finding
- **WHEN** an agent, test, or script resolves a review finding
- **THEN** the system MUST provide deterministic non-interactive inputs for the decision
- **AND** the command MUST NOT require an interactive prompt

#### Scenario: User skips a review card
- **WHEN** a user skips a review card
- **THEN** the system MUST leave the underlying finding unresolved
- **AND** the finding MUST remain eligible for a later review run

#### Scenario: No reviewable findings remain
- **WHEN** a user enters the guided review workflow and all findings are resolved, notices, or blocked maintenance
- **THEN** the system MUST state that no human review cards are currently pending for the selected scope

### Requirement: Automatic repair MUST be local, source-verified, and conservative

The system MUST perform automatic repair only for cases it can handle locally and safely, and MUST keep ambiguous content decisions reviewable by a human.

#### Scenario: Automatic maintenance refreshes indexing state
- **WHEN** audit identifies missing or stale semantic embeddings or retrieval metadata
- **THEN** the system MUST provide an automatic maintenance path that refreshes the affected index state without requiring page-by-page human review

#### Scenario: Automatic OCR retry improves extracted text
- **WHEN** a user requests automatic repair for selected pages and the source PDF is available with a matching fingerprint
- **THEN** the system MUST try local extraction or OCR candidates for those pages
- **AND** the system MUST replace stored page text and chunks only when the selected candidate scores materially better than the existing extraction
- **AND** the system MUST refresh affected retrieval metadata after replacement

#### Scenario: Automatic OCR retry does not improve extracted text
- **WHEN** automatic repair cannot produce a materially better candidate for a selected page
- **THEN** the system MUST keep or create a human review finding rather than marking the issue solved automatically

#### Scenario: Automatic repair is blocked by source status
- **WHEN** a user requests automatic OCR repair for a book whose source PDF is missing, mismatched, or unverified
- **THEN** the system MUST refuse automatic page repair for that book
- **AND** the system MUST explain the source status and available relink or re-ingest path

### Requirement: Manual replacement MUST regenerate derived rules data

The system MUST let users provide corrected text for failed OCR pages through an inline editor, `--text-file`, or stdin, and MUST rebuild all derived page/chunk retrieval state for the affected page.

#### Scenario: User replaces page text through any supported input
- **WHEN** a user provides corrected text for a selected book page through an inline editor, `--text-file`, or stdin
- **THEN** the system MUST store the corrected text as local rules-corpus data
- **AND** the system MUST regenerate chunks, page audit metadata, retrieval metadata, and semantic index coverage for the affected page as needed
- **AND** future queries MUST use the corrected text rather than the failed OCR text

#### Scenario: User replaces text with empty or unusable content
- **WHEN** a user attempts to replace page text with empty or unusable content
- **THEN** the system MUST reject the replacement or require an explicit exclude/ignore decision instead

### Requirement: Source PDF relink MUST support moved local files

The system MUST provide a way to update the stored source PDF path for an ingested book without copying the PDF into the vault.

#### Scenario: User relinks the same PDF at a new path
- **WHEN** a user provides a new PDF path for an ingested book and the fingerprint matches the ingested source fingerprint
- **THEN** the system MUST update the stored source PDF path
- **AND** future audit and repair runs MUST treat the source as available

#### Scenario: User relinks a different PDF
- **WHEN** a user provides a new PDF path whose fingerprint differs from the ingested source fingerprint
- **THEN** the system MUST require explicit user confirmation before using that source for repair
- **AND** the system MUST preserve enough status information for audit to explain that the repair source differs from the original ingestion source

### Requirement: Rules query MUST honor review exclusions

The system MUST keep reviewed retrieval exclusions consistent across exact and semantic rules retrieval.

#### Scenario: Query matches an excluded chunk
- **WHEN** `backet rules query` would otherwise return a chunk excluded through audit review
- **THEN** the excluded chunk MUST NOT appear in primary or fallback query results

#### Scenario: Excluded chunks are present in JSON metadata
- **WHEN** a JSON audit or query result reports retrieval quality metadata
- **THEN** the result MUST include enough deterministic metadata for an agent or test to explain that reviewed exclusions affected eligibility

### Requirement: JSON audit output MUST remain deterministic

The system MUST preserve machine-readable `--json` output for audit, review, repair, and source status commands.

#### Scenario: Agent audits rules as JSON
- **WHEN** a user or agent runs `backet --json rules audit`
- **THEN** stdout MUST contain deterministic JSON with structured source status, maintenance findings, review findings, notices, review decisions, and repair hints
- **AND** stdout MUST NOT contain human prompts, Rich formatting, or progress text

#### Scenario: Human audit output is bounded
- **WHEN** a user runs non-JSON audit commands
- **THEN** the human output MUST remain bounded by default
- **AND** the output MUST provide a path to inspect full details through JSON or focused review commands

### Requirement: Scope audit MUST summarize reviewable scope suggestions separately

The system MUST render non-JSON `backet rules scope audit` output as a bounded summary of generated scope assertions without mixing scope curation into extraction-quality repair.

#### Scenario: Scope audit has suggested assertions
- **WHEN** a user runs `backet rules scope audit` for a book with suggested assertions
- **THEN** the human output MUST summarize applied, suggested, rejected, and review-needed scope assertions
- **AND** the output MUST show bounded examples of notable suggestions with page, tag, role, status, and confidence

#### Scenario: User needs full scope assertion details
- **WHEN** a user needs to inspect or edit the full scope assertion set
- **THEN** the scope audit output MUST guide the user toward the deterministic export/apply workflow or any focused scope review command available in the implementation
