## Why

The planner currently falls back to raw tokens when it does not know a term, which lets phrases like "Blush of Life" degrade into unrelated matches for `life`, `alive`, or `scene`. Rules retrieval needs to resolve named mechanics, powers, disciplines, rituals, and target groups before searching for answer evidence.

## What Changes

- Add a local rules entity catalog built from structured corpus blocks and curated seed aliases.
- Update query planning to resolve user language into canonical entities, aliases, entity types, source locations, target groups, and unresolved high-value terms.
- Replace broad first-pass retrieval with entity-first retrieval: resolve target, retrieve exact target blocks, then expand to bounded parent/neighbor/system blocks only when needed.
- Prevent raw fallback, semantic-only, or generic cue matches from being marked answerable without a resolved entity or explicit direct evidence.
- Expose entity resolution and target-first retrieval diagnostics in JSON and QA traces.

## Capabilities

### New Capabilities

- `rules-entity-catalog`: local catalog of canonical rules entities, aliases, source anchors, and rebuild diagnostics.

### Modified Capabilities

- `rules-query`: resolve entities and target groups before retrieval and expose unresolved high-value terms.
- `hybrid-rules-retrieval`: use target-first retrieval and stricter answerability gates.
- `answer-quality-diagnostics`: expose entity resolution and target-first retrieval diagnostics for QA.

## Impact

- Affected code: rules indexing, query planner, scope taxonomy, retrieval candidate generation/reranking, evidence packet creation, diagnostics, QA evaluator tests.
- Affected data: per-vault `.backet` rules store gains a rebuildable entity catalog and alias provenance. Curated seed aliases ship with the CLI; generated entries are rebuilt from ingested local corpus text.
- Dependencies: this change should be applied after `rebuild-rules-corpus-structure` so catalog entries can anchor to clean rule blocks.
- Non-goals: this change does not replace final answer synthesis; it ensures the evidence packet is much less likely to call the wrong source answerable.
