## ADDED Requirements

### Requirement: QA-normalized trace fields
Answer diagnostics SHALL expose normalized fields that allow the QA workbench to evaluate each pipeline stage without parsing human prose except for final answer text assertions.

#### Scenario: QA evaluates retrieval
- **WHEN** a QA case checks selected evidence anchors
- **THEN** the answer trace exposes selected evidence labels, book IDs, page ranges, section labels, canonical entity anchors, match reasons, and rejection reasons

#### Scenario: QA evaluates synthesis
- **WHEN** a QA case checks final answer support
- **THEN** the answer trace exposes response class, answerability status, synthesis mode, fallback reason, cited source IDs, and final answer text

#### Scenario: QA evaluates model fallback
- **WHEN** model synthesis is attempted
- **THEN** the answer trace exposes model ID, validation status, validation error code, and whether fallback output became the visible answer

### Requirement: Report-safe failure context
Answer diagnostics SHALL provide enough bounded context for QA reports to explain failures without leaking full source material or secrets.

#### Scenario: Failure report generated
- **WHEN** a QA report includes failed stage details
- **THEN** it includes source labels, page metadata, stable fingerprints, and bounded snippets but excludes raw PDFs, full rulebook text, Discord tokens, model prompts, and private file paths unless explicitly requested in local debug mode
