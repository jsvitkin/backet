## ADDED Requirements

### Requirement: Bot QA execution surface
The bot tooling SHALL provide a local QA execution surface that runs case files through the same bundle export and answer runtime used by `bot playground`.

#### Scenario: QA runs against a vault
- **WHEN** a user runs a QA suite against a vault
- **THEN** the system exports a temporary bundle and evaluates answers through the bot runtime

#### Scenario: QA runs against an existing bundle
- **WHEN** a user runs a QA suite against an exported bundle
- **THEN** the system evaluates the bundle without rebuilding vault indexes

