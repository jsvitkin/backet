## ADDED Requirements

### Requirement: Runtime service metadata in bundles
Bot bundles SHALL include non-secret runtime profile and model service metadata sufficient for doctor and benchmark commands.

#### Scenario: Bundle exported with local quality profile
- **WHEN** a vault configured for local quality runtime is exported
- **THEN** the bundle manifest includes profile, fallback policy, service roles, endpoint environment names, and model IDs without model binaries or secrets

### Requirement: Model files remain external
Bot bundle export SHALL NOT include local model files, model caches, or runtime installation artifacts.

#### Scenario: Model path configured
- **WHEN** bot config references a local model path or Ollama model ID
- **THEN** export records metadata only and reports that model files are external runtime dependencies

