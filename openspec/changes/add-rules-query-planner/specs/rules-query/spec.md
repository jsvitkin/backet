## ADDED Requirements

### Requirement: Rules queries MUST create a query plan before retrieval
The system MUST plan natural-language rules questions before retrieving rule chunks.

#### Scenario: Plan a user question
- **WHEN** a user asks a rules question through the CLI or Discord bot runtime
- **THEN** the system MUST derive a query plan containing normalized text, detected intent, canonical terms, expanded terms, retrieval queries, scope tags, and required evidence hints

#### Scenario: Preserve raw question
- **WHEN** a query plan is created
- **THEN** the plan MUST retain the raw user question for diagnostics and fallback retrieval

#### Scenario: Planning remains local
- **WHEN** a query plan is created
- **THEN** the system MUST create it locally without sending the question, rule chunks, vault content, or rulebook text to a remote service

### Requirement: Query planning MUST normalize common rules aliases
The system MUST normalize common rules aliases, compounds, plurals, and punctuation variants into canonical query terms.

#### Scenario: Compound term normalized
- **WHEN** a question contains `bloodbonds`
- **THEN** the query plan MUST include canonical and expanded terms for `blood bond` and `blood bonds`

#### Scenario: Discipline term normalized
- **WHEN** a question contains a known discipline name such as `Obfuscate`
- **THEN** the query plan MUST include the matching discipline scope tag and canonical discipline term

#### Scenario: Clan term normalized
- **WHEN** a question contains a known clan plural such as `Malkavians`
- **THEN** the query plan MUST include the matching clan scope tag and canonical clan term

### Requirement: Query planning MUST classify answer intent
The system MUST classify the kind of rules evidence needed by the question.

#### Scenario: Advancement question
- **WHEN** a question asks how a character learns or acquires a discipline or power
- **THEN** the query plan MUST mark advancement or acquisition intent and include retrieval queries for advancement rules in addition to the named discipline

#### Scenario: Targeting question
- **WHEN** a question asks whether a power can affect another type of target
- **THEN** the query plan MUST mark targeting or applicability intent and include retrieval queries for system text, target restrictions, and the named power or mechanic

#### Scenario: Definition question
- **WHEN** a question asks what a named mechanic is
- **THEN** the query plan MUST mark definition intent and prefer retrieval queries likely to find definitions over incidental mentions

### Requirement: Planned retrieval MUST reduce low-value query terms
The system MUST prevent low-value user phrasing from dominating rules retrieval.

#### Scenario: Generic verbs are downweighted
- **WHEN** a question contains generic verbs such as `use`, `make`, or `learn`
- **THEN** the query plan MUST either downweight those terms or use them only inside intent-specific retrieval queries

#### Scenario: Raw fallback is retained
- **WHEN** planned queries are generated
- **THEN** the raw query MAY remain available as a fallback, but planned canonical queries MUST be distinguishable from the raw fallback in diagnostics

### Requirement: Query plans MUST be diagnosable
The system MUST expose query planning diagnostics to local machine-readable workflows.

#### Scenario: JSON query includes plan
- **WHEN** a user or agent runs a rules query or local bot answer in JSON mode
- **THEN** the output MUST include the query plan or a diagnostic explaining why planning was unavailable

#### Scenario: Planning ambiguity detected
- **WHEN** a planner detects multiple plausible canonical meanings
- **THEN** the plan MUST include an ambiguity warning rather than silently discarding competing interpretations
