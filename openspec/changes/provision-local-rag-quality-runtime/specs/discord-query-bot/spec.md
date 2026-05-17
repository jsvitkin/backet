## ADDED Requirements

### Requirement: Quality profile runtime enforcement
The bot runtime SHALL enforce required local model service roles according to the configured runtime profile.

#### Scenario: Lite profile degraded answer
- **WHEN** lite profile runs without model services
- **THEN** the bot may use deterministic fallback and diagnostics mark the answer as degraded

#### Scenario: Quality profile service missing
- **WHEN** quality profile requires a model service that is unavailable
- **THEN** the bot returns runtime-unavailable rather than silently using template-only answers

### Requirement: Benchmark traces
Bot answer traces SHALL include enough runtime timing and model-service metadata for local benchmark reports.

#### Scenario: Local model answer generated
- **WHEN** a local answer model produces a response
- **THEN** the trace includes answer mode, model ID, endpoint role, elapsed time, validation status, and fallback status

