## Why

The Prague traces show source chunks with noisy section labels, page headers, sheet/lore bleed, and metadata that had to be refreshed after code changes. Retrieval cannot become reliable unless the rules corpus has a clear repair, reindex, and reingest workflow.

## What Changes

- Add a rules corpus health report that identifies stale metadata, noisy chunks, low-quality section labels, missing semantic indexes, and likely reingest candidates.
- Improve chunk metadata classification so navigation pages, sheets, lore, discipline headings, and system blocks are separated more reliably.
- Add a migration/reindex path that refreshes retrieval metadata without requiring source PDFs.
- Add a repair path that tells the user exactly when source PDFs are needed for reingestion or OCR repair.
- Add source-window cleanup so answer snippets favor nearby rule text rather than page furniture or unrelated paragraphs.
- Add tests that prove reindexing is enough for metadata/schema changes and reingestion is only requested for unusable stored text.

## Capabilities

### New Capabilities

### Modified Capabilities
- `rules-ingestion`: Adds corpus repair/reingest requirements and better chunk metadata generation.
- `rules-audit`: Adds retrieval-quality and reingest-needed diagnostics.
- `hybrid-rules-retrieval`: Requires cleaner metadata and source windows for candidate ranking.
- `rules-query`: Reports corpus health blockers that prevent reliable answers.

## Impact

- Affected CLI: `backet rules audit`, `backet rules index`, and possibly a new `backet rules corpus doctor/repair` command.
- Affected per-vault state: `.backet/rules/rules.sqlite3` stores refreshed metadata and indexes; source PDFs remain external user-owned files.
- Affected workflows: users may need to run `backet rules index --full`; reingest is requested only when stored chunks are structurally unusable or source fingerprints need repair.
- Affected tests: corpus health fixtures, migration tests, and QA cases that depend on clean source windows.

