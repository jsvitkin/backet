## ADDED Requirements

### Requirement: Entity-first candidate generation
Hybrid rules retrieval SHALL generate answer candidates from resolved entity anchors before broad lexical, semantic, or raw fallback channels.

#### Scenario: Target block exists
- **WHEN** the query plan resolves a named power or mechanic to source blocks
- **THEN** retrieval includes those target blocks before considering broad fallback matches

#### Scenario: System text in neighbor block
- **WHEN** the target block contains the heading and a bounded neighbor contains its system text
- **THEN** retrieval may include the neighbor block as selected evidence with a structured expansion reason

#### Scenario: Broad fallback only
- **WHEN** only broad fallback or semantic-only matches are available for a resolved-entity question
- **THEN** retrieval reports those matches as fallback context and does not mark the evidence answerable unless direct entity and intent evidence gates pass

### Requirement: Stricter answerability gates
Hybrid rules retrieval SHALL mark evidence answerable only when selected evidence covers the resolved entity, requested intent, and required situational constraints.

#### Scenario: Generic duration match
- **WHEN** a query asks about `Blush of Life` and a candidate only contains `Duration: One scene` without the resolved entity or equivalent source anchor
- **THEN** the candidate is rejected or kept as fallback context, not selected answer evidence

#### Scenario: Related edge-case power
- **WHEN** a query asks about base `Dominate` eye-contact requirements and a candidate only describes a special Famulus delivery power
- **THEN** retrieval does not answer from that candidate unless it also identifies the base rule relationship or reports the scope as a special case

#### Scenario: Target group not covered
- **WHEN** a question asks whether a rule affects Kindred and selected evidence never addresses Kindred, vampires, or the requested target group
- **THEN** the evidence packet is insufficient with missing target-group evidence

### Requirement: Entity-first retrieval diagnostics
Hybrid rules retrieval SHALL report how selected evidence was connected to the resolved entity and intent.

#### Scenario: Evidence selected
- **WHEN** selected evidence is returned
- **THEN** diagnostics include target entity IDs, expansion reasons, satisfied intent evidence, satisfied target constraints, and rejected high-scoring fallback candidates

#### Scenario: Evidence insufficient
- **WHEN** evidence is insufficient
- **THEN** diagnostics include unresolved entities, missing intent evidence, missing target constraints, and closest fallback sources without presenting them as selected evidence
