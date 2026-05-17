## Context

The rules bot already uses local ingestion, chunk metadata, exact search, embeddings, reranking, and answerability gates. The remaining failure pattern is not "no embeddings"; it is that a chunk is still too blunt a retrieval object. A chunk can contain a real rule, an example, a lore paragraph, an adjacent heading, and a named power on the same page, and the system has to infer the role of each passage at answer time.

This change adds a derived mechanics layer over the existing rules corpus. Source PDFs stay external. Raw chunks and existing vector or exact indexes stay available. Rule units live in per-vault state under `.backet/rules/` as rebuildable derived data linked back to chunk IDs, book metadata, page ranges, and heading paths.

## Goals / Non-Goals

**Goals:**
- Represent answerable mechanics as structured rule units with source traceability.
- Separate base rules, specific powers, examples, exceptions, table rows, and flavor/lore before retrieval.
- Preserve auditable raw chunks so every rule unit can be inspected against source text.
- Let existing vaults derive rule units from stored chunks when source PDFs are not present.
- Expose human-readable and JSON diagnostics for coverage, confidence, stale schema versions, and low-quality extraction.

**Non-Goals:**
- Do not replace SQLite, JSON storage, exact search, or embeddings.
- Do not make the Discord bot smarter by itself; query planning and synthesis changes consume this layer later.
- Do not attempt a complete VTM ontology or full legal/rules normalization pass.
- Do not commit copyrighted source text to the repo or copy PDFs into the vault.

## Decisions

1. Store rule units as rebuildable per-vault rules state.

   Rule units belong with the ingested rules corpus under `.backet/rules/`, not in canonical Obsidian notes and not in the repository. They are derived from user-owned source PDFs or stored chunks, so they can be rebuilt and versioned by schema. This keeps campaign canon separate from rules indexes and keeps private source material local.

   Alternative considered: write generated Markdown notes for each rule unit. That would make inspection pleasant, but it risks turning derived data into apparent canon and could leak copyrighted text into vault content.

2. Use rule units as an additional retrieval object, not as a replacement for chunks.

   Exact chunk retrieval, vector chunk retrieval, metadata filters, and neighbor expansion remain useful. Rule units add a mechanics-aware layer that can be exact-searched, vector-searched, and filtered by kind, authority role, entity tags, and facets. Retrieval can still include source chunks as bounded evidence windows.

   Alternative considered: migrate immediately to a dedicated vector database. That would not solve the distinction between "mention" and "answerable rule", and it would add hosting and migration complexity before the data model is correct.

3. Keep extraction deterministic first, with optional model assistance behind diagnostics.

   The first implementation should use headings, cue phrases, table structure, chunk metadata, and known entity aliases before calling a local model. If local model assistance is used for classification or facet extraction, the output must include confidence, schema version, source hash, and extraction warnings so it can be rebuilt and audited.

   Alternative considered: ask a model to summarize every chunk into mechanics records. That is faster to prototype, but it creates opaque errors and makes QA harder.

4. Treat authority role and answer facets as first-class fields.

   The critical distinction is often not the entity name but the role of the text: base rule, specific rule, exception, example, optional rule, or flavor. Rule units also need facets such as cost, dice pool, target, duration, effect, limit, prerequisite, and consequence so later answerability can check whether the packet can answer the question.

   Alternative considered: store only better tags on chunks. Tags help retrieval, but they do not stop answer synthesis from mixing unrelated sentences inside the same chunk.

5. Keep terminal UX concise and JSON complete.

   Human output for derivation and diagnostics should summarize books processed, chunks inspected, units created, stale units refreshed, low-confidence counts, and the next command to inspect details. JSON output should include complete unit IDs, source IDs, schema versions, confidence, warning codes, and coverage counts without raw dict/list rendering.

## Risks / Trade-offs

- [Risk] Extraction mistakes create false precision. Mitigation: keep source chunk links, confidence, warning codes, and diagnostics; retrieval must be allowed to fall back to chunks.
- [Risk] Derived data grows large. Mitigation: store compact records, bounded source snippets or hashes, and schema-versioned rebuild paths.
- [Risk] Model-assisted extraction varies by local runtime. Mitigation: prefer deterministic extraction and store extraction backend/model metadata when a model contributes.
- [Risk] Table rows and multi-page powers are hard to segment. Mitigation: support multi-source units and extraction warnings instead of pretending every unit is clean.
- [Risk] Existing vaults may lack source PDFs. Mitigation: rebuild from stored chunks where sufficient and report when original PDFs are required for missing text or OCR recovery.

## Migration Plan

1. Add the rule-unit schema and schema-version metadata to the per-vault rules store.
2. Implement derivation from stored chunks and RAG metadata.
3. Hook derivation into rules ingestion and rules index refresh.
4. Add diagnostics and JSON output for coverage, stale records, low confidence, and source linkage.
5. Update retrieval to read rule units as an optional channel while preserving existing chunk-only behavior if no units exist.
6. Rollback by ignoring or deleting the derived rule-unit state; raw chunks and existing indexes remain usable.

## Open Questions

None for the proposal. The implementation should choose the exact storage tables/files based on the current rules store layout.
