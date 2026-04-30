## 1. Progress Event Plumbing

- [x] 1.1 Define a small rules ingestion progress event model or callback protocol for phase, message, current count, total count, and counters
- [x] 1.2 Thread the optional progress callback through `ingest_rulebook` without changing existing callers that do not need progress
- [x] 1.3 Emit progress events for PDF inspection and selected page scope before per-page extraction starts
- [x] 1.4 Emit progress events during page extraction, including current page count, total selected pages, OCR count, and suspect/review count
- [x] 1.5 Emit progress events for chunk storage, search index rebuild, and final audit-summary phases

## 2. CLI Progress Rendering

- [x] 2.1 Add a human-mode rules ingest progress reporter that writes live status/progress to stderr
- [x] 2.2 Ensure `backet --json rules ingest` does not write human progress to stdout
- [x] 2.3 Implement automatic first-slice progress behavior: Rich progress for interactive human runs and plain phase lines for non-interactive non-JSON runs, with no new `--progress` option
- [x] 2.4 Keep the progress renderer presentation-specific so `rules.py` does not import Rich or terminal UI helpers

## 3. Human Completion Report

- [x] 3.1 Add a rules-ingest-specific human completion renderer instead of using the generic `emit_success()` data dump
- [x] 3.2 Show book identity, tier, processed page count, chunk count, source PDF, and rules store location first
- [x] 3.3 Summarize long OCR and suspect page lists with counts and bounded previews
- [x] 3.4 Omit empty optional diagnostics from human output
- [x] 3.5 Label OCR pages as pages that required OCR and suspect pages as pages needing review or low-confidence review
- [x] 3.6 Include audit follow-up guidance when pages need review

## 4. Tests

- [x] 4.1 Add unit tests for progress event emission across inspect, extraction, OCR fallback, storage, indexing, and summary phases
- [x] 4.2 Add CLI tests proving human ingest emits visible progress/status output during a run
- [x] 4.3 Add CLI tests proving non-interactive non-JSON ingest emits plain phase/status lines
- [x] 4.4 Add CLI tests proving JSON ingest stdout remains parseable and complete
- [x] 4.5 Add completion-report tests for long page-list summarization, empty diagnostic omission, and human-friendly labels
- [x] 4.6 Add or update fixture-based tests for a multi-page PDF with OCR fallback and suspect pages

## 5. Documentation and Validation

- [x] 5.1 Update README or CLI usage docs with the improved human ingest behavior and JSON-output boundary
- [x] 5.2 Update smoke validation if needed so install-safe ingestion still exercises the command with the new output behavior
- [x] 5.3 Run the focused rules tests and the full test suite
- [x] 5.4 Run `openspec status --change improve-rules-ingest-terminal-ux` and confirm the change is ready to apply
