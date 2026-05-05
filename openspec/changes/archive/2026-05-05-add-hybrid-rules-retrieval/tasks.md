## 1. Rules Semantic Storage

- [x] 1.1 Add a rule embedding schema migration under `.backet/rules/rules.sqlite3` keyed by chunk id, backend, model, dimensions, content hash, `embedding_json`, and timestamp
- [x] 1.2 Add helpers for detecting missing and stale rule embeddings without mutating raw rule chunks
- [x] 1.3 Reuse the existing local embedding backend abstraction for rule chunks and preserve deterministic hash-backend behavior for tests
- [x] 1.4 Ensure embedding generation never sends rule text to remote services
- [x] 1.5 Add rebuildable retrieval-quality metadata storage for section kind and ranking flags

## 2. Rules Indexing and Status

- [x] 2.1 Build embeddings for newly ingested or repaired rule chunks when a local backend is available
- [x] 2.2 Add a rebuild path for existing rule stores with missing or stale rule embeddings
- [x] 2.3 Add deterministic JSON metadata for embedding backend, model, indexed chunk count, missing count, and stale count
- [x] 2.4 Implement `backet rules index <vault> [--book-id <id>] [--full]` for semantic coverage reporting and refresh
- [x] 2.5 Keep rules ingestion usable when semantic indexing is unavailable, while reporting exact-only fallback clearly
- [x] 2.6 Keep `rules audit` focused on extraction quality while pointing to `backet rules index` when semantic coverage is missing or stale

## 3. Hybrid Rules Query

- [x] 3.1 Add semantic candidate retrieval over rule chunk embeddings
- [x] 3.2 Merge semantic candidates with existing FTS/BM25 candidates by chunk id
- [x] 3.3 Add ranking reasons and scores for exact, semantic, metadata, scope, precedence, and quality factors
- [x] 3.4 Preserve existing primary/fallback result shape and ambiguity errors for agent compatibility
- [x] 3.5 Add quality-aware penalties using stored retrieval metadata for suspect OCR, very short chunks, and navigational or non-answer sections
- [x] 3.6 Expose query retrieval mode and semantic backend/model in machine-readable output

## 4. Skill Pack Alignment

- [x] 4.1 Update `workflow-authoring` to triage source needs across vault canon, rules, and external research before drafting
- [x] 4.2 Update working brief guidance to separate `Canon says`, `Rules suggest`, `External research`, and `Open choices`
- [x] 4.3 Update `city-foundation` examples or guidance so they inherit the multi-source workflow without turning the skill into a district/domain authoring workflow
- [x] 4.4 Preserve skill guidance that vault canon is authoritative and rules ambiguity must be surfaced rather than guessed
- [x] 4.5 Confirm skill updates remain compatible with the existing skill-pack manifest and independent `backet skills update` flow

## 5. Tests

- [x] 5.1 Add unit tests for rule embedding schema creation, stale detection, and local backend selection
- [x] 5.2 Add fixture-based tests proving conceptual rules queries can return semantic-only matches while exact rule queries still prioritize exact matches
- [x] 5.3 Add tests proving supplement precedence and ambiguity behavior still apply after hybrid candidate gathering
- [x] 5.4 Add ranking tests proving suspect OCR, tiny chunks, TOC/index/sheet chunks, and art-heavy chunks are downranked when substantive rule text exists
- [x] 5.5 Add JSON contract tests for retrieval mode, backend/model metadata, and match reasons
- [x] 5.6 Add workflow asset tests for source-lane triage and the expanded working brief sections

## 6. Documentation and Validation

- [x] 6.1 Update README guidance for local semantic rules retrieval and the optional Sentence Transformers backend
- [x] 6.2 Document that Backet owns local vault/rules retrieval while agents perform cited external research when needed
- [x] 6.3 Run focused rules, retrieval, workflow asset, and skill tests
- [x] 6.4 Run the full test suite
- [x] 6.5 Run `openspec status --change add-hybrid-rules-retrieval` and confirm the change is apply-ready
