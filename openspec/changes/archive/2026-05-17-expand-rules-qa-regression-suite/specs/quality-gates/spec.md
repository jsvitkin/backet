## ADDED Requirements

### Requirement: Required answer QA gate
The project quality gates SHALL include a required fixture-backed rules answer QA suite that fails validation when committed answer behavior regresses.

#### Scenario: Required QA suite fails
- **WHEN** a required rules answer QA case fails
- **THEN** the validation command exits non-zero and reports the earliest failed pipeline stage

#### Scenario: Required QA suite passes
- **WHEN** all required rules answer QA cases pass
- **THEN** the validation command reports pass totals by category and difficulty

### Requirement: Non-blocking local calibration suites
The project quality gates SHALL keep private-vault and model-backed calibration suites outside mandatory CI unless explicitly enabled.

#### Scenario: Local calibration missing
- **WHEN** local calibration configuration references an unavailable vault, bundle, or model service
- **THEN** CI treats those cases as skipped rather than failed

#### Scenario: Local calibration enabled
- **WHEN** an operator explicitly enables local calibration suites
- **THEN** failures include the same stage classification as required cases
