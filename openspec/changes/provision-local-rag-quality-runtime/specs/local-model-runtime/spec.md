## ADDED Requirements

### Requirement: Local runtime doctor
The system SHALL inspect local model runtime availability, GPU/backend status, configured service endpoints, model IDs, and required profile roles.

#### Scenario: Native Ollama available
- **WHEN** Ollama is installed and serving its local API
- **THEN** the doctor reports the endpoint, available models, backend status when available, and profile compatibility

#### Scenario: Runtime missing
- **WHEN** no configured local runtime is available
- **THEN** the doctor reports the missing service roles and the install command or manual action needed

### Requirement: Local benchmark
The system SHALL benchmark configured local model services using bot QA questions and resource metrics.

#### Scenario: Benchmark runs
- **WHEN** a user runs the benchmark against a vault or bundle
- **THEN** the system records model IDs, runtime backend, answer latency, tokens per second when available, peak memory when available, and QA pass/fail results

#### Scenario: Benchmark output requested as JSON
- **WHEN** the benchmark runs with `--json`
- **THEN** output includes deterministic per-case metrics and an aggregate hardware recommendation summary

### Requirement: Machine-local model storage
The system SHALL keep downloaded model files and runtime caches outside the repo and outside canonical vault notes.

#### Scenario: Model cache configured
- **WHEN** a model cache path is configured
- **THEN** bot config stores only the path or endpoint metadata and does not add model binaries to Git-tracked deployment bundles

### Requirement: Runtime profile compatibility
The system SHALL classify local runtime compatibility for lite, standard, and quality profiles.

#### Scenario: Quality profile missing reranker
- **WHEN** the answer and embedding services are available but the reranker is missing
- **THEN** the quality profile is not compatible and the standard profile may be compatible if configured to degrade

