## ADDED Requirements

### Requirement: Bot deployment MUST support RAG runtime profiles
The system MUST let operators choose and inspect the runtime quality profile used by the hosted bot.

#### Scenario: Lite profile configured
- **WHEN** a bot bundle or setup state uses the lite profile
- **THEN** the system MUST support template answers and low-resource retrieval without requiring heavyweight model services

#### Scenario: RAG standard profile configured
- **WHEN** a bot bundle or setup state uses a standard RAG profile
- **THEN** the system MUST require compatible semantic retrieval support and MAY allow deterministic or lightweight reranking and optional model synthesis according to configuration

#### Scenario: RAG quality profile configured
- **WHEN** a bot bundle or setup state uses a quality RAG profile
- **THEN** the system MUST require configured embedding, reranker, and answer model capabilities or fail closed according to profile policy

#### Scenario: Runtime profile inspectable
- **WHEN** a Storyteller runs bot health or doctor diagnostics
- **THEN** the system MUST report the active profile, required services, service health, fallback policy, and any degraded mode

### Requirement: Model service compatibility MUST be doctorable
The system MUST verify configured model-service capabilities before deployment or startup.

#### Scenario: Embedding service checked
- **WHEN** semantic retrieval is required by the active profile
- **THEN** doctor checks MUST verify that the configured embedding backend or service can embed sample text and matches expected compatibility metadata

#### Scenario: Reranker service checked
- **WHEN** reranking is required by the active profile
- **THEN** doctor checks MUST verify that the configured reranker can score a bounded sample candidate set within configured timeouts

#### Scenario: Answer model checked
- **WHEN** model answer synthesis is required by the active profile
- **THEN** doctor checks MUST verify that the configured answer model endpoint can produce a bounded completion within configured timeouts

#### Scenario: Service unavailable
- **WHEN** a required model service is unavailable or incompatible
- **THEN** deployment or startup diagnostics MUST fail clearly or mark the runtime degraded according to profile policy

### Requirement: Runtime profile metadata MUST stay out of secrets
The system MUST distinguish non-secret model-service metadata from secrets and private data.

#### Scenario: Manifest records compatibility metadata
- **WHEN** a bundle is exported with a RAG runtime profile
- **THEN** the manifest MUST record non-secret profile, backend, model identifier, dimensions, endpoint role, and compatibility metadata needed for startup checks

#### Scenario: Secrets excluded
- **WHEN** model services require credentials
- **THEN** tokens, SSH keys, private download credentials, and API keys MUST NOT be written into the bundle manifest, Git-tracked deploy assets, or bot data bundle

#### Scenario: Model files excluded
- **WHEN** deployment uses local model files
- **THEN** model weights MUST remain in a VM-local or operator-controlled model cache and MUST NOT be copied into the bot data bundle

### Requirement: Hosted RAG runtime MUST preserve private-data boundaries
The hosted bot MUST use only user-controlled runtime services in the initial RAG hosting upgrade.

#### Scenario: Self-hosted model service
- **WHEN** the hosted bot sends retrieved rule or vault snippets to an embedding, reranker, or answer model service
- **THEN** the service MUST be configured as local or self-hosted within the operator-controlled deployment boundary

#### Scenario: Third-party service requested
- **WHEN** configuration requests a third-party hosted model API
- **THEN** the initial implementation MUST reject it or mark it unsupported until a separate privacy and licensing decision explicitly enables that mode

### Requirement: Runtime degradation MUST be explicit
The hosted bot MUST not silently fall back to a lower-quality mode.

#### Scenario: Optional service fails
- **WHEN** an optional service fails and profile policy allows fallback
- **THEN** the bot MUST answer through the configured fallback and report degraded mode in diagnostics

#### Scenario: Required service fails
- **WHEN** a required service fails and profile policy is fail-closed
- **THEN** the bot MUST refuse affected answers with a runtime-unavailable message rather than silently using weaker retrieval or synthesis
