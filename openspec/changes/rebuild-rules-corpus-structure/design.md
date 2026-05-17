## Context

The current retrieval failures are not only model failures. The source corpus often exposes chunks as broad pages with headings such as `VA M P I R E S`, repeated page headers, and passages that mix multiple rules. A query can retrieve the correct page while the answer composer sees the wrong sentence. This change focuses on the corpus layer: turn extracted pages into reusable rule blocks with clean boundaries and source metadata.

The CLI owns ingestion, reindexing, and audit commands. Per-vault state under `.backet/` stores extracted text and derived metadata. Source PDFs stay outside the vault and are only read during ingestion or explicit reingestion.

## Goals / Non-Goals

**Goals:**

- Produce rule blocks with stable IDs, heading paths, block kind, source page ranges, clean text, and quality metadata.
- Preserve enough page linkage to cite book/page accurately.
- Rebuild structure metadata from stored text when possible.
- Tell the operator when reindexing is enough and when source PDF reingestion is needed.

**Non-Goals:**

- Do not build the full entity catalog in this change.
- Do not change final answer synthesis behavior except where it consumes cleaner source windows.
- Do not require remote OCR, remote embeddings, or copying source PDFs into the vault.

## Decisions

1. Add a rule-block abstraction beside existing chunk compatibility.
   - Decision: store normalized rule blocks while retaining compatibility fields used by existing query output.
   - Rationale: later changes need precise block IDs, but current callers should not break mid-migration.
   - Alternative considered: replace chunks outright. Rejected because it would make the change too risky and harder to roll back.

2. Derive structure locally and rebuildably.
   - Decision: use text extraction, heading heuristics, page cues, typography hints when available, and stored chunk text for reindexing.
   - Rationale: users should not need source PDFs for every metadata schema bump.
   - Alternative considered: require reingestion for all existing stores. Rejected because source PDFs may not be available during routine maintenance.

3. Treat tables and lists as structured text, not noise.
   - Decision: preserve compact row/list boundaries and tag block kind when a rule table or list is detected.
   - Rationale: many rule answers live in trait-cost tables, duration rows, or power stat blocks.

4. Audit corpus structure separately from answer quality.
   - Decision: add audit diagnostics for page furniture, broad headings, empty blocks, mixed rule blocks, stale structure metadata, and reingest candidates.
   - Rationale: bad answer QA should be able to point to corpus repair instead of blaming synthesis.

## Risks / Trade-offs

- [Risk] Heading heuristics mis-split unusual supplements. → Mitigation: retain source page metadata, provide audit review output, and keep reingestion/reindexing idempotent.
- [Risk] SQLite schema migration disrupts existing vaults. → Mitigation: preserve compatibility output and add migration tests against old stores.
- [Risk] Cleaner blocks reduce recall for broad questions. → Mitigation: retrieval can still expand to parent/neighbor blocks under bounded rules.

## Migration Plan

1. Add schema support for block metadata and compatibility projection.
2. Implement structure rebuild from stored chunk text.
3. Update ingestion to emit structured blocks for new imports.
4. Update audit/index commands to report stale or missing block metadata.
5. Document when to run reindex versus source-PDF reingestion.

## Open Questions

- None. The architecture choice is to keep source PDFs external and make stored text reindexable whenever possible.
