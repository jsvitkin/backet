## ADDED Requirements

### Requirement: Broad standard rules QA suites
The rules answer QA workbench SHALL provide versioned case suites that cover normal player-session rules questions across difficulty bands, categories, and answerability outcomes.

#### Scenario: Standard suite has coverage metadata
- **WHEN** the standard rules QA suite is loaded
- **THEN** each case declares difficulty, category, command route, expected answerability, expected first failure stage when applicable, and whether the case is required or exploratory

#### Scenario: Difficulty bands are represented
- **WHEN** the standard suite is validated
- **THEN** it includes required or exploratory cases for very easy, easy, medium, hard, and very hard questions

#### Scenario: Negative cases are represented
- **WHEN** the standard suite is validated
- **THEN** it includes cases where the correct behavior is insufficiency, ambiguity, or conflict rather than a substantive answer

### Requirement: Case assertions cover pipeline stages
The rules answer QA workbench SHALL evaluate planner, retrieval, answerability, synthesis, citation, runtime, and output-policy assertions independently.

#### Scenario: Evidence is correct but answer is wrong
- **WHEN** selected evidence satisfies the case anchors but the visible answer omits the required stance or claim
- **THEN** the case fails at synthesis or claim-support stage rather than retrieval

#### Scenario: Retrieval is related but insufficient
- **WHEN** retrieved sources mention query terms but selected evidence does not satisfy required entity and intent anchors
- **THEN** the case fails at answerability stage

#### Scenario: Model path falls back
- **WHEN** a model answer is rejected and fallback output is used
- **THEN** the case result records the model validation error and evaluates the final visible answer separately

### Requirement: Suite execution modes
The rules answer QA workbench SHALL distinguish CI-required suites from local exploratory and private-vault calibration suites.

#### Scenario: Required fixture suite runs in CI
- **WHEN** repository validation runs the required rules QA suite
- **THEN** it executes without private vault paths, source PDFs, or external model services

#### Scenario: Private vault suite is unavailable
- **WHEN** a private-vault calibration suite references a missing local vault path
- **THEN** the workbench reports the suite as skipped without failing CI

#### Scenario: Exploratory suite reports regressions
- **WHEN** an exploratory suite fails
- **THEN** the human and JSON reports identify failures but the command exits non-zero only when exploratory failures are explicitly promoted

### Requirement: Fresh-question calibration support
The rules answer QA workbench SHALL support ad hoc fresh-question runs that produce gradeable reports without adding those questions to the committed suite.

#### Scenario: User runs ad hoc questions
- **WHEN** a user supplies multiple questions and a grading output path
- **THEN** the workbench evaluates each question, records stage diagnostics, and writes a report artifact without modifying committed case files

#### Scenario: Ad hoc report references suite gaps
- **WHEN** an ad hoc question fails in a category not represented by required cases
- **THEN** the report identifies the missing category so maintainers can decide whether to add a permanent case
