## 1. Per-vault index foundation

- [x] 1.1 Design the durable SQLite-backed index schema for note metadata, chunks, search data, and retrieval bookkeeping
- [x] 1.2 Implement Markdown parsing and chunking based on file paths and heading structure
- [x] 1.3 Add local embedding generation and storage for vault note chunks

## 2. Staleness and refresh handling

- [x] 2.1 Add source fingerprinting so external vault edits can invalidate stale indexed state
- [x] 2.2 Implement manual indexing and incremental refresh behavior for stale vault state
- [x] 2.3 Add recovery behavior for missing rebuildable local artifacts on new machines

## 3. Context bundle retrieval

- [x] 3.1 Implement exact, semantic, metadata, and hierarchy-aware retrieval composition
- [x] 3.2 Add `backet context` output modes for human-readable and deterministic machine-readable responses
- [x] 3.3 Add tests covering exact canon lookup, semantic lookup, scope-bounded bundle assembly, and stale-state refresh behavior

## 4. Derived memory capsules

- [x] 4.1 Define initial scoped memory capsule families and their source-reference format
- [x] 4.2 Implement memory generation and rebuild commands under `.backet/memory/`
- [x] 4.3 Verify that durable memory artifacts are committable while scratch artifacts remain ignored

## 5. Retrieval quality coverage

- [x] 5.1 Add unit tests for chunk selection, ranking composition, and scope-filter logic
- [x] 5.2 Add integration tests using representative vault fixtures with external-edit and reindex scenarios
- [x] 5.3 Add regression tests for committed index portability and machine-readable context output
