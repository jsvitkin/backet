## ADDED Requirements

### Requirement: Answer-quality regression gate
The project quality gates SHALL include a rules answer QA suite that can fail local validation when required cases regress.

#### Scenario: Required case fails
- **WHEN** a required QA case fails in the standard suite
- **THEN** the validation command exits non-zero and identifies the failed stage

#### Scenario: Private vault case is unavailable
- **WHEN** a QA case references a local vault path that does not exist
- **THEN** the validation reports the case as skipped rather than failing CI

