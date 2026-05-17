## ADDED Requirements

### Requirement: QA workbench MUST run archetype case sets
The rules answer QA workbench MUST load, validate, filter, execute, and report archetype-based rules QA case sets.

#### Scenario: Archetype case file loads
- **WHEN** a user runs the QA workbench with a valid archetype case file
- **THEN** the workbench MUST validate archetype, difficulty, answer class, evidence facets, contract expectations, and variant metadata before executing cases

#### Scenario: Filter by archetype
- **WHEN** a user requests a QA run for a specific archetype or difficulty
- **THEN** the workbench MUST execute only matching cases and report the active filter

### Requirement: QA workbench MUST grade diagnostics before answer text
The QA workbench MUST evaluate scenario frame, evidence contract, selected evidence, answerability, and missing facets before applying final answer text checks.

#### Scenario: Retrieval fails before text
- **WHEN** a case lacks required evidence in diagnostics
- **THEN** the workbench MUST classify the failure before final answer text checks and report the missing facets

#### Scenario: Evidence passes but answer text fails
- **WHEN** diagnostics satisfy required evidence facets but final text contradicts the expected answer class
- **THEN** the workbench MUST classify the failure as synthesis or output policy

### Requirement: QA workbench reports MUST include archetype summaries
The QA workbench MUST include archetype, difficulty, evidence contract, answerability, and stage summaries in human and JSON output.

#### Scenario: Human output grouped by archetype
- **WHEN** archetype QA completes without JSON output
- **THEN** the workbench MUST show pass/fail totals grouped by archetype and difficulty with concise failure names and next debug commands

#### Scenario: JSON output includes contract fields
- **WHEN** archetype QA completes in JSON mode
- **THEN** each result MUST include archetype, difficulty, evidence contract ID, required facets, satisfied facets, missing facets, stage classification, and selected source summaries
