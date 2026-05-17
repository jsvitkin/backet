## 1. Entity Catalog

- [x] 1.1 Add local catalog schema/resources for canonical entity name, entity type, aliases, source anchors, scope tags, provenance, content hash, and schema version.
- [x] 1.2 Add curated seed aliases for common/core mechanics and the observed failure areas, including Rouse Check, Hunger, Blush of Life, Dominate, Dementation, Blood Bond, and discipline power variants.
- [x] 1.3 Generate catalog entries from structured rule blocks during `backet rules index --full`.
- [x] 1.4 Add ambiguity detection for aliases that map to multiple comparable entities.

## 2. Query Planning

- [x] 2.1 Update query planning to resolve entities before retrieval and expose resolved/unresolved terms in JSON output.
- [x] 2.2 Extract target groups and situational constraints such as Kindred targets, eye contact, touch, scene duration, and Hunger state.
- [x] 2.3 Preserve unresolved high-value phrases as answerability blockers instead of reducing them to generic raw tokens.
- [x] 2.4 Add planner tests for Blush of Life, Dominate eye contact, Rouse Check, Hunger 5, blood bonds, and ambiguous aliases.

## 3. Retrieval And Answerability

- [x] 3.1 Update candidate generation to retrieve resolved target blocks before broad fallback channels.
- [x] 3.2 Add bounded parent/neighbor expansion for target blocks whose system text spans nearby blocks.
- [x] 3.3 Prevent raw fallback and semantic-only matches from proving answerability without direct entity and intent evidence.
- [x] 3.4 Add diagnostics for entity-first retrieval, target constraints, missing evidence, and rejected fallback candidates.

## 4. Verification

- [x] 4.1 Add integration tests proving `Blush of Life` does not retrieve unrelated one-scene powers as selected evidence.
- [x] 4.2 Add integration tests proving base Dominate targeting is not answered from an unrelated special delivery power.
- [x] 4.3 Run the expanded QA suite and record which remaining failures belong to synthesis rather than retrieval.
- [x] 4.4 Run `openspec validate --all --strict`.

Validation notes:

- Added query planner coverage for Blush of Life, Dominate eye contact, Hunger 5, and seed entity diagnostics.
- Added integration coverage for Blush of Life target-block retrieval and base Dominate targeting versus a special Famulus delivery distractor.
- Prague screenshot-regression QA after the full apply passed 4/5; the remaining required failure is retrieval-stage Dementation targeting.
- Configured-model exploratory `standard-fresh` QA passed 1/5; failures are split across synthesis and retrieval, with Dominate eye-contact still retrieval-sensitive.
- `openspec validate add-rules-entity-first-retrieval --strict` passed.
