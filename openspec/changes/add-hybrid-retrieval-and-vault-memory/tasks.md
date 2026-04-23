## 1. Per-vault index foundation

- [ ] 1.1 Design the durable SQLite-backed index schema for note metadata, chunks, search data, and retrieval bookkeeping
- [ ] 1.2 Implement Markdown parsing and chunking based on file paths and heading structure
- [ ] 1.3 Add local embedding generation and storage for vault note chunks

## 2. Staleness and refresh handling

- [ ] 2.1 Add source fingerprinting so external vault edits can invalidate stale indexed state
- [ ] 2.2 Implement manual indexing and incremental refresh behavior for stale vault state
- [ ] 2.3 Add recovery behavior for missing rebuildable local artifacts on new machines

## 3. Context bundle retrieval

- [ ] 3.1 Implement exact, semantic, metadata, and hierarchy-aware retrieval composition
- [ ] 3.2 Add `backet context` output modes for human-readable and deterministic machine-readable responses
- [ ] 3.3 Add tests covering exact canon lookup, semantic lookup, scope-bounded bundle assembly, and stale-state refresh behavior

## 4. Derived memory capsules

- [ ] 4.1 Define initial scoped memory capsule families and their source-reference format
- [ ] 4.2 Implement memory generation and rebuild commands under `.backet/memory/`
- [ ] 4.3 Verify that durable memory artifacts are committable while scratch artifacts remain ignored

## 5. Retrieval quality coverage

- [ ] 5.1 Add unit tests for chunk selection, ranking composition, and scope-filter logic
- [ ] 5.2 Add integration tests using representative vault fixtures with external-edit and reindex scenarios
- [ ] 5.3 Add regression tests for committed index portability and machine-readable context output
