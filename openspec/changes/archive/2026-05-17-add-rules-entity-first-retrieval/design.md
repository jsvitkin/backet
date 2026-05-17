## Context

The current planner recognizes some taxonomy entries but lacks a durable catalog of rule entities and source anchors. Unknown high-value phrases are kept as raw searchable terms, and retrieval can mark weak matches answerable when generic evidence cues such as `system` or `duration` appear nearby. This change inserts an explicit resolution step before retrieval.

The CLI owns catalog building and query planning. The catalog is local and rebuildable from the user's ingested corpus plus repository seed aliases. It does not include source PDF files and does not send rulebook text to remote services.

## Goals / Non-Goals

**Goals:**

- Resolve named rules entities before retrieval, including mechanics, disciplines, powers, rituals, ceremonies, formulae, clans, target groups, and aliases.
- Anchor retrieval to target blocks and only expand to bounded neighbors or parent system blocks.
- Treat unresolved high-value terms as diagnostic blockers or ambiguity, not as permission to answer from generic text.
- Preserve source precedence and existing bounded retrieval behavior.

**Non-Goals:**

- Do not create a fully normalized rules database for every mechanic.
- Do not hand-author every possible VTM term before generated catalog support exists.
- Do not let model synthesis override unresolved or insufficient evidence.

## Decisions

1. Build a hybrid generated-plus-curated catalog.
   - Decision: ship curated seed aliases for common/core mechanics and generate source-anchored entries from structured rule blocks.
   - Rationale: the system needs immediate coverage for known problem areas while still scaling to user-owned supplements.
   - Alternative considered: pure manual catalog. Rejected because it would become stale and incomplete.

2. Make entity resolution a formal planner stage.
   - Decision: the query plan includes resolved entities, unresolved high-value terms, target groups, ambiguity warnings, and resolution confidence.
   - Rationale: answerability cannot be judged if the system does not know what rule object the user asked about.

3. Retrieval starts at the target entity.
   - Decision: candidate generation first retrieves exact target blocks by entity ID or accepted alias, then adds bounded parent/neighbor/system blocks.
   - Rationale: this prevents unrelated `Duration: One scene` or `eye contact` snippets from winning over the actual rule target.

4. Raw fallback cannot prove answerability by itself.
   - Decision: raw fallback and semantic-only matches can provide debug/fallback context but cannot be selected evidence unless they pass direct entity and intent evidence gates.
   - Rationale: fallback exists for recall, not for false confidence.

## Risks / Trade-offs

- [Risk] Strict entity requirements may abstain on valid obscure rules. → Mitigation: expose unresolved terms clearly and allow curated aliases to be added quickly.
- [Risk] Generated aliases create collisions. → Mitigation: store alias provenance and ambiguity warnings; require narrowing when collisions are comparable.
- [Risk] Catalog rebuild adds indexing time. → Mitigation: make it incremental and content-hash based.

## Migration Plan

1. Add catalog tables/resources and seed aliases.
2. Build catalog entries from structured rule blocks during rules indexing.
3. Update query planner output schema with resolution fields.
4. Update retrieval candidate generation and answerability gating.
5. Update QA cases for Blush of Life, Dominate eye contact, Rouse Check, Hunger 5, and similar normal-session questions.

## Open Questions

- None. The resolver should be deterministic and local; model-assisted entity extraction can be explored later only as an optional bounded enhancement.
