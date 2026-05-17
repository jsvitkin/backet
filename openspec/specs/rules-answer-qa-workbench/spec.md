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

