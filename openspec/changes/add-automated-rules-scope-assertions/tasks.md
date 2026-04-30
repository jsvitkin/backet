## 1. Schema and Vocabulary

- [x] 1.1 Add rules-store schema migration for durable scope assertions and any chunk/assertion mapping needed by query paths
- [x] 1.2 Backfill existing book-level `scope_tags_json` values as migrated source assertions for older rules stores
- [x] 1.3 Add a VTM-focused typed scope taxonomy resource with canonical tags, aliases, role constraints, and normalization helpers
- [x] 1.4 Add configurable confidence constants for auto-applied, suggested, and low-confidence assertions
- [x] 1.5 Add tests for scope tag normalization, alias canonicalization, unknown suggestions, confidence bands, and migration fallback

## 2. Scope Generation

- [x] 2.1 Extract reusable PDF outline and page-heading signals from the existing rules ingestion flow
- [x] 2.2 Implement local heuristic scope assertion generation from outline entries, section labels, page headings, aliases, and mechanics/lore markers
- [x] 2.3 Assign assertion roles, confidence, status, and evidence for source, mechanical-authority, setting-authority, perspective, and mention cases
- [x] 2.4 Apply high-confidence assertions to affected chunks while preserving suggested and review-needed assertions separately
- [x] 2.5 Add fixture tests using a synthetic mixed-scope supplement with sect, clan, ritual, loresheet, perspective, and institutional-mechanic sections

## 3. Ingestion and Persistence

- [x] 3.1 Thread scope generation into `backet rules ingest` after extraction/chunking and before final query metadata is reported
- [x] 3.2 Remove manual `--scope-tag` input from `backet rules ingest` and rely on generated scope assertions plus review/apply corrections
- [x] 3.3 Persist generated assertions and applied chunk scopes in SQLite under `.backet/rules/` without copying or depending on source PDFs
- [x] 3.4 Backfill minimal source assertions for existing ingested books from current book-level scope tags
- [x] 3.5 Add deterministic JSON ingest output fields for generated, applied, suggested, and review-needed assertion counts
- [x] 3.6 Update human ingest completion output to summarize generated scopes and point to the review command when needed

## 4. Review Commands

- [x] 4.1 Add `backet rules scope audit` or equivalent to summarize source scope, applied assertions, suggested assertions, review-needed spans, and confidence distribution
- [x] 4.2 Add a scope export command that emits an inspectable machine-readable manifest for a book on demand
- [x] 4.3 Add a scope apply command that validates reviewed manifests before updating durable rules state
- [x] 4.4 Refresh affected FTS/retrieval metadata after reviewed scope changes are applied
- [x] 4.5 Add CLI tests for audit, export, apply, invalid manifests, and deterministic JSON behavior

## 5. Query and Precedence

- [x] 5.1 Update exact and semantic candidate gathering to use applied chunk-level scope assertions for scope filters where available
- [x] 5.2 Update ranking to boost authoritative assertion matches and report scope assertion match reasons
- [x] 5.3 Prevent perspective and mention assertions from satisfying mechanical supplement precedence
- [x] 5.4 Fall back to book-level source-scope hints when chunks have no applied scope assertions and report that fallback in machine-readable output
- [x] 5.5 Add ambiguity tests proving comparable authoritative supplement matches still surface conflicts while perspective-only matches do not create false precedence

## 6. Validation and Documentation

- [x] 6.1 Update README or CLI usage docs to explain automated scope assertions, source hints, and review workflow
- [x] 6.2 Add or update smoke coverage so install-safe rules ingestion exercises scope generation without private PDFs
- [x] 6.3 Run the focused rules test suite and the full project test suite
- [x] 6.4 Run `openspec status --change add-automated-rules-scope-assertions` and confirm the change is ready to apply
