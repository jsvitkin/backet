## 1. Data Model And Migration

- [x] 1.1 Design and add SQLite schema support for rule block IDs, heading paths, block kind, clean text, source page range, structure schema version, and quality metadata.
- [x] 1.2 Add compatibility projection so existing query output fields still work while backed by structured blocks.
- [x] 1.3 Add migration tests for older rules stores with only chunk-level metadata.

## 2. Ingestion And Reindexing

- [x] 2.1 Implement heading and block-boundary detection for extracted rulebook text.
- [x] 2.2 Preserve rule table/list labels and discipline/ritual stat block fields in clean text and metadata.
- [x] 2.3 Implement `backet rules index --full` rebuild of structure metadata from stored text.
- [x] 2.4 Detect and report stores that require source-PDF reingestion instead of reindexing.

## 3. Audit And Retrieval Integration

- [x] 3.1 Extend rules audit with block-structure health, stale metadata, and reindex/reingest recommendations.
- [x] 3.2 Update hybrid retrieval to prefer structured blocks and clean source windows when available.
- [x] 3.3 Report corpus structure blockers in rules query and bot answer diagnostics.
- [x] 3.4 Keep human command output concise and JSON output deterministic.

## 4. Verification

- [x] 4.1 Add fixture tests for section-aware block extraction, page furniture removal, table/list preservation, and split heading/system blocks.
- [x] 4.2 Add integration tests for reindexing an old store without source PDFs.
- [x] 4.3 Run the expanded required QA suite from `expand-rules-qa-regression-suite` and record which failures remain expected for later changes.
- [x] 4.4 Run `openspec validate --all --strict`.

Validation notes:

- Added focused tests for rule-block cleaning, source-window behavior, and `rules index --full` rebuilding missing structure from stored text.
- Ran the focused rules/bot/QA cluster and then the full test suite with `pytest -q` successfully after all apply changes.
- Prague screenshot-regression QA after the full apply passed 4/5; `malkavian-dementation-targeting` remains a retrieval failure because the selected evidence still lacks the required direct targeting source.
- `openspec validate rebuild-rules-corpus-structure --strict` passed.
