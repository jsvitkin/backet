## ADDED Requirements

### Requirement: QA-consumable answer diagnostics
Answer diagnostics SHALL expose normalized fields for planner terms, retrieval mode, semantic quality, evidence status, selected source anchors, answer mode, fallback reason, and response class.

#### Scenario: Workbench reads diagnostics
- **WHEN** the QA workbench evaluates a bot answer
- **THEN** it can classify the answer without parsing human-facing Discord text except for final answer pattern checks

### Requirement: Failure reasons remain paste-safe
Answer diagnostics SHALL avoid raw source PDF paths, secrets, full source passages, Discord tokens, and unbounded user text.

#### Scenario: Diagnostic report is shared
- **WHEN** a user shares a QA failure report
- **THEN** the report contains source labels, page metadata, fingerprints, and bounded snippets only

