## 1. Entity Catalog

- [ ] 1.1 Add local catalog schema/resources for canonical entity name, entity type, aliases, source anchors, scope tags, provenance, content hash, and schema version.
- [ ] 1.2 Add curated seed aliases for common/core mechanics and the observed failure areas, including Rouse Check, Hunger, Blush of Life, Dominate, Dementation, Blood Bond, and discipline power variants.
- [ ] 1.3 Generate catalog entries from structured rule blocks during `backet rules index --full`.
- [ ] 1.4 Add ambiguity detection for aliases that map to multiple comparable entities.

## 2. Query Planning

- [ ] 2.1 Update query planning to resolve entities before retrieval and expose resolved/unresolved terms in JSON output.
- [ ] 2.2 Extract target groups and situational constraints such as Kindred targets, eye contact, touch, scene duration, and Hunger state.
- [ ] 2.3 Preserve unresolved high-value phrases as answerability blockers instead of reducing them to generic raw tokens.
- [ ] 2.4 Add planner tests for Blush of Life, Dominate eye contact, Rouse Check, Hunger 5, blood bonds, and ambiguous aliases.

## 3. Retrieval And Answerability

- [ ] 3.1 Update candidate generation to retrieve resolved target blocks before broad fallback channels.
- [ ] 3.2 Add bounded parent/neighbor expansion for target blocks whose system text spans nearby blocks.
- [ ] 3.3 Prevent raw fallback and semantic-only matches from proving answerability without direct entity and intent evidence.
- [ ] 3.4 Add diagnostics for entity-first retrieval, target constraints, missing evidence, and rejected fallback candidates.

## 4. Verification

- [ ] 4.1 Add integration tests proving `Blush of Life` does not retrieve unrelated one-scene powers as selected evidence.
- [ ] 4.2 Add integration tests proving base Dominate targeting is not answered from an unrelated special delivery power.
- [ ] 4.3 Run the expanded QA suite and record which remaining failures belong to synthesis rather than retrieval.
- [ ] 4.4 Run `openspec validate --all --strict`.
