# rules-answer-qa-workbench Specification

## Purpose
TBD - created by archiving change add-rules-answer-qa-workbench. Update Purpose after archive.
## Requirements
### Requirement: QA case files
The system SHALL load rules answer QA cases from JSON files that define question text, command route, difficulty, expected answer class, required planner terms, required source anchors, required answer patterns, forbidden answer patterns, and optional runtime profile constraints.

#### Scenario: Valid case file loads
- **WHEN** a user runs the QA workbench with a valid case file
- **THEN** the system reports the number of loaded cases and evaluates each case in deterministic order

#### Scenario: Invalid case file is rejected
- **WHEN** a case file is missing required fields or uses an unsupported schema version
- **THEN** the system fails before running bot queries and reports the invalid field path

### Requirement: Stage-level failure classification
The system SHALL classify each failed QA case by the earliest failed stage among planner, retrieval, answerability, synthesis, citation, runtime, or output policy.

#### Scenario: Planner drops a required entity
- **WHEN** a case requires the term `dementation` and the answer trace query plan does not preserve that term or an accepted alias
- **THEN** the case fails with stage `planner`

#### Scenario: Retrieval misses required anchors
- **WHEN** the planner is acceptable but no selected or fallback rule source matches the required book/page or anchor constraints
- **THEN** the case fails with stage `retrieval`

#### Scenario: Answer text contradicts expected stance
- **WHEN** retrieval sources are acceptable but the visible answer matches a forbidden pattern or omits a required stance
- **THEN** the case fails with stage `synthesis`

### Requirement: Workbench reports
The system SHALL provide concise human output and complete JSON output for QA runs.

#### Scenario: Human report summarizes failures
- **WHEN** a user runs the workbench without `--json`
- **THEN** the output lists pass/fail totals, failed case names, failure stages, and the next command or config action to investigate

#### Scenario: JSON report includes traces
- **WHEN** a user runs the workbench with `--json`
- **THEN** the output includes each case result, answer trace summary, stage failure details, selected source summaries, and generated answer diagnostics

### Requirement: Optional report artifacts
The system SHALL optionally write QA reports as derived artifacts under a user-selected output path or vault-local `.backet/reports/answer-quality/`.

#### Scenario: Report output requested
- **WHEN** a user passes a report output path
- **THEN** the system writes machine-readable results and a Markdown summary without modifying canonical vault notes

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

### Requirement: Claim-level QA assertions
The rules answer QA workbench SHALL evaluate whether final answers are supported by validated claims.

#### Scenario: Required claim missing
- **WHEN** a QA case defines a required claim pattern or stance and synthesis does not produce a validated matching claim
- **THEN** the case fails at claim-support or synthesis stage

#### Scenario: Unsupported final text
- **WHEN** final answer text includes a substantive statement not mapped to a validated claim
- **THEN** the case fails at synthesis stage

#### Scenario: Correct abstain
- **WHEN** a QA case expects insufficient evidence and no validated claim is produced
- **THEN** the case passes if the final answer abstains and does not include unsupported substantive rules advice

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

