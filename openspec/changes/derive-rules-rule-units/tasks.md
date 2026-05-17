## 1. Data Model And Storage

- [ ] 1.1 Inspect the current rules store layout and choose the rule-unit persistence shape that fits existing `.backet/rules/` patterns.
- [ ] 1.2 Add schema-versioned rule-unit records with stable unit IDs, source chunk IDs, source hashes, book/page metadata, heading path, unit kind, authority role, tags, facets, confidence, and warnings.
- [ ] 1.3 Add stale-detection helpers for unit schema version, source content hash, and missing required source metadata.
- [ ] 1.4 Ensure rule-unit state is treated as rebuildable per-vault derived data and no source PDFs or proprietary long passages are copied into the repo.

## 2. Rule-Unit Derivation

- [ ] 2.1 Implement deterministic rule-unit extraction from stored chunk text, headings, evidence cues, entity aliases, table cues, and RAG metadata.
- [ ] 2.2 Classify unit kinds including base rule, discipline power, ritual, formula, ceremony, merit, flaw, table row, exception, example, and flavor/lore.
- [ ] 2.3 Classify authority roles including base, specific, exception, optional, example, and flavor.
- [ ] 2.4 Extract answer facets for cost, dice pool, target, duration, effect, limit, prerequisite, consequence, and source reference where present.
- [ ] 2.5 Preserve multi-source units and low-confidence extraction warnings instead of flattening unclear text into confident units.
- [ ] 2.6 Add optional local-model-assisted classification only if it can store backend/model metadata, confidence, and deterministic fallback behavior.

## 3. Ingestion And Index Refresh

- [ ] 3.1 Hook rule-unit derivation into successful rules ingestion after chunks and RAG metadata are available.
- [ ] 3.2 Extend rules index refresh to create missing rule units from stored chunks.
- [ ] 3.3 Extend rules index refresh to update stale units when chunk hashes or rule-unit schema versions change.
- [ ] 3.4 Report when source PDFs are required because stored chunk text is insufficient, without copying PDFs into the vault.
- [ ] 3.5 Keep human ingestion/index output concise and add complete JSON output for derivation counts and warnings.

## 4. Retrieval Integration

- [ ] 4.1 Add a rule-unit candidate channel to hybrid rules retrieval when rule units are available.
- [ ] 4.2 Rank rule-unit candidates using exact terms, semantic similarity where available, metadata filters, entity tags, authority role, unit kind, answer facets, and source precedence.
- [ ] 4.3 Include linked source chunk IDs and bounded source labels/snippets with selected rule-unit evidence.
- [ ] 4.4 Preserve chunk-only fallback behavior and diagnostics when a vault has no rule units.

## 5. Diagnostics And CLI UX

- [ ] 5.1 Add rule-unit diagnostics that summarize books inspected, chunks inspected, units created, stale units, low-confidence units, orphaned chunks, and suspected adjacent-text bleed.
- [ ] 5.2 Add machine-readable diagnostics with deterministic counts, warning codes, unit IDs, chunk IDs, schema versions, and bounded source labels.
- [ ] 5.3 Add or update inspection commands for a single rule unit and its linked source chunks.
- [ ] 5.4 Add regression coverage proving non-JSON command output does not dump raw dictionaries, lists, machine payload keys, full source passages, or source PDF paths.

## 6. Tests And Documentation

- [ ] 6.1 Add unit tests for rule-unit extraction, classification, facet extraction, source traceability, stale detection, and low-confidence warnings.
- [ ] 6.2 Add integration tests for ingestion/index refresh creating and refreshing rule units from stored chunks.
- [ ] 6.3 Add retrieval tests proving base-rule units outrank example/flavor mentions and specific mechanic units outrank broad mentions for specific questions.
- [ ] 6.4 Add documentation for what rule units are, where they live, how to rebuild them, and how to inspect diagnostics.
- [ ] 6.5 Run the focused test suite and OpenSpec validation for this change.
