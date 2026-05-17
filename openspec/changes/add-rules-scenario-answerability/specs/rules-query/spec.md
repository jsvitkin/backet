## ADDED Requirements

### Requirement: Query planning MUST include scenario-frame data
Rules query planning MUST add scenario-frame fields to the query plan for scenario-shaped rules questions.

#### Scenario: JSON query includes scenario frame
- **WHEN** a user or agent runs a rules query in machine-readable mode for a scenario-shaped question
- **THEN** the output MUST include actor, action, target, mechanic or entity, conditions, polarity, requested answer shape, frame confidence, and ambiguity warnings when available

#### Scenario: Simple definition remains simple
- **WHEN** a user asks a simple definition question that does not need a scenario frame
- **THEN** the query plan MUST either provide a minimal definition frame or explicitly mark scenario framing as not required

### Requirement: Query planning MUST select evidence contracts
Rules query planning MUST select an evidence contract that corresponds to the user's question archetype and required answer facets.

#### Scenario: Interaction contract selected
- **WHEN** a user asks how two rules, powers, or conditions interact
- **THEN** the query plan MUST select an interaction evidence contract and include retrieval hints for both mechanics and any precedence or exception evidence

#### Scenario: Contract selection unavailable
- **WHEN** the planner cannot select a reliable evidence contract
- **THEN** the query plan MUST include a diagnostic reason and downstream stages MUST treat answerability as degraded or insufficient

### Requirement: Query diagnostics MUST distinguish framing and retrieval failures
Rules query diagnostics MUST expose whether a failure occurred during scenario framing, contract selection, retrieval, evidence assembly, or synthesis.

#### Scenario: Framing failure
- **WHEN** the planner cannot identify the requested mechanic or action
- **THEN** diagnostics MUST mark the earliest failed stage as scenario framing or planning rather than retrieval

#### Scenario: Retrieval failure after valid frame
- **WHEN** the planner creates a valid scenario frame but retrieval finds no required source evidence
- **THEN** diagnostics MUST mark retrieval or evidence assembly as the failing stage and include missing facets
