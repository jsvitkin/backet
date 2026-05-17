## ADDED Requirements

### Requirement: Query planning resolves rules entities
Rules query planning SHALL resolve high-value user terms to catalog entities before candidate retrieval.

#### Scenario: Named mechanic resolved
- **WHEN** a user asks about a named mechanic such as `Blush of Life`
- **THEN** the query plan includes the resolved entity ID, canonical name, entity type, accepted aliases, and source anchors

#### Scenario: Named discipline resolved
- **WHEN** a user asks about a discipline such as `Dominate`
- **THEN** the query plan includes the discipline entity and any requested rule aspect such as targeting, cost, dice pool, or restriction

#### Scenario: Unresolved high-value term
- **WHEN** a user question contains an unknown high-value phrase that appears to be a rule name
- **THEN** the query plan preserves that phrase as unresolved and warns that retrieval cannot prove answerability from generic fallback alone

### Requirement: Query planning extracts target groups
Rules query planning SHALL extract target groups and situational constraints that affect answerability.

#### Scenario: Other vampires target group
- **WHEN** a user asks whether a power works on other vampires
- **THEN** the query plan preserves a target group such as `vampire`, `kindred`, or `other vampires`

#### Scenario: Eye contact constraint
- **WHEN** a user asks about using a power without eye contact
- **THEN** the query plan preserves `eye contact` or an accepted contact/targeting constraint as required evidence

### Requirement: Query plan exposes resolution diagnostics
Rules query planning SHALL expose entity resolution diagnostics in machine-readable output.

#### Scenario: JSON query plan returned
- **WHEN** a rules query or bot answer runs in JSON mode
- **THEN** the query plan includes resolved entities, unresolved high-value terms, target groups, alias provenance, ambiguity warnings, and resolution confidence
