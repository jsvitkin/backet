## ADDED Requirements

### Requirement: Archetype QA cases MUST classify player-question shape
The system MUST represent rules QA cases with a question archetype, difficulty, expected answer class, and evidence-contract expectations.

#### Scenario: Case declares archetype
- **WHEN** a QA case is loaded
- **THEN** the case MUST declare an archetype such as definition, procedure, cost, resource quantity, targeting, restriction, interaction, base-vs-specific, cross-reference, conflict, or insufficiency

#### Scenario: Case declares difficulty
- **WHEN** a QA case is loaded
- **THEN** the case MUST declare a difficulty usable for reports and filtered runs

### Requirement: Archetype QA expectations MUST use evidence facets
Archetype QA cases MUST express required evidence facets, accepted source roles, forbidden source roles, answerability expectations, and final answer checks.

#### Scenario: Targeting case requires target evidence
- **WHEN** a targeting QA case is evaluated
- **THEN** the evaluator MUST fail the case if diagnostics do not show target evidence or an appropriate insufficiency outcome

#### Scenario: Base rule case forbids specific-only evidence
- **WHEN** a base-rule QA case is evaluated
- **THEN** the evaluator MUST fail the case if the answer relies only on a specific power, example, or flavor source where base-rule evidence is required

### Requirement: Archetype QA MUST support prompt variants
The system MUST support deterministic prompt variants for each archetype so QA can test generalized behavior rather than only fixed prompt strings.

#### Scenario: Variant prompt evaluated
- **WHEN** a QA run includes variants
- **THEN** the report MUST identify the base case, variant ID or seed, archetype, difficulty, and result

#### Scenario: Variant preserves contract
- **WHEN** a prompt variant changes phrasing or synonyms
- **THEN** the variant MUST preserve the same evidence contract unless it declares a different expected contract

### Requirement: Archetype QA MUST classify failure modes
The system MUST classify failed archetype QA cases by earliest failed stage, missing facets, answerability status, source role problem, and final answer text problem.

#### Scenario: Flavor source used as rule
- **WHEN** an answer uses flavor or example evidence as if it were authoritative mechanics evidence
- **THEN** the case MUST fail with a source-role failure classification

#### Scenario: Missing evidence answered confidently
- **WHEN** required facets are missing but the answer presents a confident supported answer
- **THEN** the case MUST fail with answerability and synthesis failure details

### Requirement: Archetype QA reports MUST summarize generalization
The system MUST report archetype QA results grouped by archetype, difficulty, evidence contract, answerability status, failure stage, and regression status.

#### Scenario: Human archetype report
- **WHEN** a user runs archetype QA without JSON
- **THEN** the report MUST summarize pass/fail totals by archetype and difficulty and list the highest-impact failures with the next debug command

#### Scenario: JSON archetype report
- **WHEN** a user or agent runs archetype QA with JSON output
- **THEN** the report MUST include each case result, variant metadata, contract expectations, diagnostics summary, selected source summaries, missing facets, and failure classifications
