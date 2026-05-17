## 1. Metadata Foundation

- [x] 1.1 Define RAG v2 metadata schema version and compatibility behavior
- [x] 1.2 Add rebuildable chunk metadata for heading paths, aliases, entity locations, and evidence cues
- [x] 1.3 Refresh metadata during rules ingest, rules repair, manual replacement, and rules index
- [x] 1.4 Add audit diagnostics for missing or stale RAG v2 metadata

## 2. Evidence Packet Model

- [x] 2.1 Define evidence packet structures for selected evidence, fallback context, rejected candidates, and evidence status
- [x] 2.2 Preserve existing primary/fallback result compatibility fields during the transition
- [x] 2.3 Add JSON serialization and human-readable debug summaries

## 3. Candidate Generation

- [x] 3.1 Add planned exact, phrase, alias, semantic, metadata, and raw fallback retrieval channels
- [x] 3.2 Add candidate caps and timing diagnostics for each retrieval channel
- [x] 3.3 Distinguish hash embeddings from production-quality semantic embeddings in diagnostics

## 4. Reranking and Evidence Gate

- [x] 4.1 Implement deterministic intent-aware reranking against query plans
- [x] 4.2 Add evidence gate statuses for answerable, insufficient, ambiguous, and conflicting
- [x] 4.3 Preserve supplement precedence and existing ambiguity behavior inside RAG v2 selection
- [x] 4.4 Add rejection reasons for mere mentions, low-quality sections, and missing evidence cues

## 5. Runtime Integration

- [x] 5.1 Route rules query CLI output through RAG v2 when metadata is available
- [x] 5.2 Route bot rules source selection through RAG v2 evidence packets
- [x] 5.3 Expose RAG v2 diagnostics in answer-quality traces

## 6. Validation

- [x] 6.1 Add unit tests for metadata classification and evidence cue detection
- [x] 6.2 Add integration tests for advancement, targeting, definition, cost, and consequence queries
- [x] 6.3 Add regression tests proving screenshot-style mere mentions are marked insufficient
- [x] 6.4 Run full tests and OpenSpec validation
