# quality-gates Specification

## Purpose
TBD - created by archiving change bootstrap-backet-foundation. Update Purpose after archive.
## Requirements
### Requirement: Automated tests MUST run on push and pull request events

The repository MUST run automated tests through GitHub Actions for code changes on push and pull request events.

#### Scenario: Validate a pushed commit

- **WHEN** a commit is pushed to a branch with an active workflow
- **THEN** GitHub Actions MUST run the configured automated test suite for that change

#### Scenario: Validate a pull request

- **WHEN** a pull request is opened, reopened, or updated
- **THEN** GitHub Actions MUST run the configured automated test suite for that pull request

### Requirement: Test coverage MUST include more than unit tests for high-risk flows

The automated validation strategy MUST include unit tests and additional integration or smoke coverage for installation, bootstrap, persistence, and other high-risk flows.

#### Scenario: Validate bootstrap and install flows

- **WHEN** the repository runs its automated validation workflows
- **THEN** the workflow MUST exercise bootstrap and installation smoke coverage in addition to narrower unit tests

### Requirement: Failed quality gates MUST block release publication

The repository MUST not publish release artifacts if required automated quality gates fail.

#### Scenario: Block a broken release

- **WHEN** required tests or install-validation jobs fail for a release candidate
- **THEN** the release publication step MUST not continue

### Requirement: Answer-quality regression gate
The project quality gates SHALL include a rules answer QA suite that can fail local validation when required cases regress.

#### Scenario: Required case fails
- **WHEN** a required QA case fails in the standard suite
- **THEN** the validation command exits non-zero and identifies the failed stage

#### Scenario: Private vault case is unavailable
- **WHEN** a QA case references a local vault path that does not exist
- **THEN** the validation reports the case as skipped rather than failing CI

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

