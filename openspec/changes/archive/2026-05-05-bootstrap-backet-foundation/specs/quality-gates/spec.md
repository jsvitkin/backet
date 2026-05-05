## ADDED Requirements

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
