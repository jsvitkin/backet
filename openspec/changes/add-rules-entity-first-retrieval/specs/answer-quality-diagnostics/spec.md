## ADDED Requirements

### Requirement: Entity resolution trace
Answer diagnostics SHALL expose entity resolution and target-first retrieval decisions for local bot answers and QA reports.

#### Scenario: Bot answer includes trace
- **WHEN** a local bot answer runs in JSON mode
- **THEN** the answer trace includes resolved entities, unresolved high-value terms, target groups, alias provenance, entity-first retrieval mode, and answerability gate results

#### Scenario: Resolution fails
- **WHEN** a bot answer abstains because a high-value term could not be resolved
- **THEN** diagnostics identify the unresolved term and closest catalog or fallback matches without presenting fallback matches as answer evidence
