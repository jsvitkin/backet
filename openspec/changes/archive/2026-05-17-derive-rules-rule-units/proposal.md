## Why

Rules QA is still brittle because retrieval works primarily with source chunks: it can find nearby text, but it cannot reliably tell whether that text is a base rule, a specific power, an example, an exception, flavor prose, or an adjacent unrelated paragraph. We need an index-time mechanics layer that makes the corpus queryable as rule units while keeping the original chunks as auditable source evidence.

## What Changes

- Add derived rule units during rules ingestion and refresh, built from the existing parsed chunks and source metadata.
- Persist rule-unit records in per-vault rules state as rebuildable derived data, with stable IDs, source chunk links, page ranges, heading paths, entity tags, mechanics tags, authority roles, and answer facets.
- Classify rule units by kind, such as base rule, discipline power, ritual, formula, ceremony, merit, flaw, table row, exception, example, and flavor or lore.
- Capture answer-relevant facets where present, including cost, dice pool, target, duration, effect, limit, prerequisite, consequence, source reference, and ambiguity or extraction warnings.
- Add diagnostics that report extraction coverage, low-confidence units, orphaned chunks, suspected adjacent-text bleed, and unit/source mismatches.
- Keep raw chunks, embeddings, exact search, and existing retrieval indexes; rule units augment retrieval rather than replacing the storage backend.
- Require a rebuild path so existing vaults can derive rule units from already-ingested rules data without manually preparing source PDFs again when chunk data is sufficient.
- Non-goal: this change does not alter final Discord answer style by itself, does not require switching vector databases, and does not introduce a complete game-rules ontology.

## Capabilities

### New Capabilities
- `rules-rule-units`: Defines derived structured rule units, their source traceability, classification, facets, persistence, rebuild behavior, and diagnostics.

### Modified Capabilities
- `rules-ingestion`: Rules ingestion must derive and refresh rule units as rebuildable per-vault rules state.
- `hybrid-rules-retrieval`: Hybrid retrieval must be able to retrieve and rank rule units alongside raw chunks without loading whole books or chapters.

## Impact

- CLI: adds rule-unit derivation during rules ingestion and a rebuild/diagnostics command surface.
- Per-vault state: stores derived rule-unit tables or documents under `.backet/` alongside existing rules indexes; machine-specific caches remain ignored.
- Ingested rules corpus: gains structured derived records that point back to book/page/chunk evidence; source PDFs remain external and are not stored in the repo.
- Skills and Discord bot: no direct behavior change required in this slice, but later query and synthesis changes can consume rule-unit evidence.
- Dependencies: may reuse local model/runtime configuration for optional extraction assistance, but the durable output must remain deterministic enough to rebuild and inspect.
