## ADDED Requirements

### Requirement: Rules questions MUST produce scenario frames
The system MUST represent rules questions as scenario frames before final answer synthesis when the question asks for applicability, procedure, cost, quantity, restriction, interaction, exception, or definition.

#### Scenario: Targeting question framed
- **WHEN** a user asks whether a named mechanic can affect a target under stated conditions
- **THEN** the scenario frame MUST identify the mechanic, target, requested polarity, relevant conditions, and targeting or applicability intent

#### Scenario: Procedure question framed
- **WHEN** a user asks how to perform a rules action during play
- **THEN** the scenario frame MUST identify the action, actor when present, requested procedure, and required procedure facets

### Requirement: Scenario frames MUST preserve ambiguity
Scenario framing MUST preserve ambiguous or competing interpretations instead of silently selecting one meaning.

#### Scenario: Multiple plausible mechanics
- **WHEN** a question text could refer to multiple known mechanics or entities
- **THEN** the scenario frame MUST include ambiguity diagnostics and the answerability stage MUST account for them

### Requirement: Evidence contracts MUST define required facets
The system MUST select an evidence contract for each scenario-shaped rules question and use that contract to define required evidence facets and acceptable source roles.

#### Scenario: Resource quantity contract
- **WHEN** a question asks how much of a resource is spent, restored, gained, or lost
- **THEN** the selected contract MUST require resource identity, amount or cost, constraints, and authoritative source evidence

#### Scenario: Negative restriction contract
- **WHEN** a question asks whether something cannot be done or is prohibited
- **THEN** the selected contract MUST require explicit restriction evidence, contradiction evidence, or an insufficiency outcome rather than treating absence of retrieval as proof

### Requirement: Evidence packets MUST be contract-aware
The system MUST assemble bounded evidence packets that satisfy the selected evidence contract before a confident answer is produced.

#### Scenario: Base and specific rules required
- **WHEN** a contract requires both a base rule and a specific mechanic
- **THEN** the evidence packet MUST include both roles or mark the corresponding facet missing

#### Scenario: Exception found
- **WHEN** retrieved evidence contains an exception relevant to the scenario frame
- **THEN** the evidence packet MUST include the exception role and expose it to answer synthesis

### Requirement: Answerability MUST expose status and missing facets
The system MUST classify scenario answerability as enough evidence, partial evidence, conflicting evidence, or insufficient evidence before final synthesis.

#### Scenario: Missing target facet
- **WHEN** retrieval finds a named power but no evidence about the requested target type
- **THEN** answerability MUST mark the target facet missing and MUST NOT allow a confident yes/no answer

#### Scenario: Conflicting evidence
- **WHEN** comparable sources conflict on a required contract facet without a precedence decision
- **THEN** answerability MUST report conflicting evidence and require an ambiguity-aware answer
