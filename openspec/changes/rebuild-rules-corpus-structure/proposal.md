## Why

The rules corpus is still too page-shaped: chunks often begin with page furniture, broad headings, or unrelated neighboring text. Retrieval and synthesis cannot reliably answer questions like "Blush of Life" or "Dominate eye contact" until ingestion produces precise rule blocks with durable structure.

## What Changes

- Rebuild rules ingestion and reindexing around structured rule blocks instead of page-like chunks.
- Persist heading hierarchy, rule block IDs, block kind, page range, extraction quality, table/list shape, and source-window metadata in the per-vault rules store.
- Add diagnostics that distinguish reindexable stores from stores that require source-PDF reingestion.
- Teach retrieval to use block boundaries and clean source windows rather than raw page starts.
- Keep all extracted corpus data local under `.backet/`; source PDFs remain external and are not copied into the vault.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `rules-ingestion`: persist section-aware rule blocks and rebuildable structure metadata.
- `rules-audit`: report corpus structure health and whether reindex or reingestion is required.
- `hybrid-rules-retrieval`: retrieve and cite clean block-centered source windows.

## Impact

- Affected code: rules PDF ingestion, stored SQLite schema or migrations, rules indexing/reindexing, audit diagnostics, retrieval result formatting, tests and fixtures.
- Affected data: per-vault `.backet` rules database gains rebuildable structural metadata. Existing stores can be reindexed when stored text is sufficient; badly broken stores are reported as reingest candidates.
- Non-goals: this change does not add entity-first retrieval or final answer claim synthesis. It creates the reliable corpus shape those later changes depend on.
