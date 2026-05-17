## ADDED Requirements

### Requirement: Synthesis diagnostics
Answer diagnostics SHALL include the answer outline, selected evidence IDs, final synthesis mode, validation status, and fallback reason.

#### Scenario: Model validation fails
- **WHEN** local model output is rejected
- **THEN** diagnostics include the validation error code and the fallback policy used

#### Scenario: Deterministic composer answers
- **WHEN** the deterministic composer produces the final answer
- **THEN** diagnostics identify the answer shape and source IDs used for each claim

### Requirement: Unsupported claim checks
Answer diagnostics SHALL expose whether final text claims are supported by selected evidence.

#### Scenario: Forbidden pattern detected
- **WHEN** final text matches a QA forbidden pattern for the case
- **THEN** the workbench can classify the failure as synthesis rather than retrieval

