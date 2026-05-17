# bot-deployment-bundles Specification

## Purpose
TBD - created by archiving change add-discord-query-bot. Update Purpose after archive.
## Requirements
### Requirement: Bot export MUST produce a read-only deployment bundle
The system MUST export a deployment bundle containing only the runtime artifacts needed by the private Discord bot.

#### Scenario: Export bot bundle
- **WHEN** a user runs the bot export command for an initialized vault
- **THEN** the system MUST create a bundle with manifest metadata, visibility policy evaluation, access-scoped vault indexes, shared rules SQLite state when configured, and deploy metadata

#### Scenario: Exclude source PDFs
- **WHEN** a vault has ingested rulebooks from source PDFs
- **THEN** the bot export MUST NOT copy source PDF files into the deployment bundle

#### Scenario: Exclude machine-specific scratch
- **WHEN** a vault contains `.backet/cache`, `.backet/temp`, `.backet/ocr-work`, model downloads, or local deploy credentials
- **THEN** the bot export MUST exclude those machine-specific or rebuildable artifacts from the deployment bundle

#### Scenario: Runtime opens bundle read-only
- **WHEN** the bot runtime loads an exported bundle
- **THEN** it MUST treat bundled SQLite databases, manifests, and policy files as read-only runtime inputs

### Requirement: Bundle manifests MUST be deterministic and complete
The system MUST write a manifest that lets humans, CI, and the bot runtime verify bundle compatibility before serving Discord requests.

#### Scenario: Manifest records provenance
- **WHEN** a bundle is exported
- **THEN** the manifest MUST include the Backet CLI version, bundle schema version, export timestamp, vault fingerprint or source revision, access policy hash, and source corpus fingerprints

#### Scenario: Manifest records retrieval compatibility
- **WHEN** a bundle contains vault or rules indexes with semantic embeddings
- **THEN** the manifest MUST record the embedding backend, embedding model, index schema versions, rules schema version, and semantic coverage metadata needed by the runtime

#### Scenario: Manifest records bot binding
- **WHEN** a bundle is exported for Discord use
- **THEN** the manifest MUST include the configured guild ID and command configuration summary without including the Discord bot token

### Requirement: Deployment inputs MUST distinguish secrets from variables
The system MUST define which deployment inputs are secrets and which are non-secret variables so guided setup can configure GitHub safely.

#### Scenario: Configure secret deploy inputs
- **WHEN** guided setup configures secret deploy inputs
- **THEN** values that grant access, such as Discord bot tokens, SSH private keys, and private model-download tokens, MUST be stored only as GitHub Actions secrets or equivalent secret storage

#### Scenario: Configure non-secret deploy inputs
- **WHEN** guided setup configures non-secret deploy inputs
- **THEN** facts such as guild ID, Oracle host, Oracle user, compose profile, deploy path, model relative path, and model checksum MAY be stored as committed setup state and GitHub repository variables

#### Scenario: Non-secret fact treated as sensitive
- **WHEN** a user chooses to hide a normally non-secret deploy fact
- **THEN** the setup wizard MUST support storing that fact as a GitHub secret or MUST clearly report that the selected hiding mode is unsupported

#### Scenario: Bundle manifest written
- **WHEN** bot export writes a bundle manifest after guided setup
- **THEN** the manifest MUST include non-secret binding and compatibility metadata but MUST NOT include GitHub secret names as authority or any secret values

### Requirement: Export diagnostics MUST support human and JSON workflows
The system MUST expose bot export and doctor diagnostics in both concise human output and deterministic machine-readable JSON.

#### Scenario: Human export summary
- **WHEN** a user runs bot export without JSON output
- **THEN** the system MUST summarize player-visible note counts, Storyteller note counts, excluded note counts, rules chunk counts, retrieval modes, model configuration status, and bundle output path

#### Scenario: JSON export summary
- **WHEN** a user or CI runs bot export with JSON output
- **THEN** the system MUST emit deterministic structured data containing bundle paths, counts, warnings, policy decisions, fingerprints, and deploy hints

#### Scenario: Export blocked by unsafe policy
- **WHEN** the access policy is invalid or would make player visibility ambiguous
- **THEN** the system MUST fail the export with a structured error and MUST NOT produce a partial deployable bundle

### Requirement: Deployment helpers MUST target Oracle VM/container hosting
The system MUST provide deployment artifacts or instructions suitable for a private Oracle Always Free VM running the bot as containers.

#### Scenario: Generate container deploy assets
- **WHEN** a user exports a bot bundle with deploy assets enabled
- **THEN** the system MUST include or reference Docker Compose configuration for the bot worker and optional local Llama service

#### Scenario: Keep secrets out of generated assets
- **WHEN** deploy assets are generated
- **THEN** the system MUST provide example environment variable names without writing real Discord tokens, SSH keys, model tokens, or deploy credentials into the bundle

#### Scenario: Support rollback
- **WHEN** a new bundle is deployed to the VM
- **THEN** the deployment layout MUST allow the operator to restart the bot against a previous bundle without rebuilding vault indexes or re-ingesting rules

#### Scenario: Model cache bootstrap
- **WHEN** the deployment configuration enables local Llama synthesis
- **THEN** the deployment assets MUST include or reference a VM-side bootstrap path that verifies or downloads the configured GGUF model into a VM-local model cache without adding the model file to the bot bundle

### Requirement: Deploy automation MUST remain private by default
The system MUST support private GitHub Actions deployment without requiring public distribution of private rules or canon data.

#### Scenario: Manual GitHub Actions deploy
- **WHEN** a user triggers the configured GitHub Actions deployment workflow manually
- **THEN** the workflow MUST export the bundle, upload it to the Oracle VM, activate the release, refresh VM-local model files when needed, restart containers, and run a smoke check

#### Scenario: Repository prerequisites documented
- **WHEN** deployment docs describe the GitHub Actions setup
- **THEN** they MUST list the required private repository contents, including vault Markdown needed for bot indexes, `.backet/config.yaml`, `.backet/rules/rules.sqlite3` when rules are enabled, bot configuration, note visibility metadata, workflow files, and deploy scripts

#### Scenario: Required secrets documented
- **WHEN** deployment docs describe the GitHub Actions setup
- **THEN** they MUST list required secrets and variables such as Oracle VM host, VM username, SSH private key, Discord token, optional model-download token, and vault path input or variable

#### Scenario: Public code image with private data volume
- **WHEN** the bot code image is built separately from the bot data bundle
- **THEN** the image MUST NOT contain private vault notes, extracted rule chunks, source PDFs, or Discord secrets

#### Scenario: Workflow artifacts remain private
- **WHEN** the GitHub Actions workflow creates a bot bundle artifact
- **THEN** it MUST treat that artifact as private to the repository/workflow and MUST NOT publish it to a public release, package registry, or container image

### Requirement: Guided deployment MUST use the private GitHub Actions workflow
The system MUST allow the setup wizard to invoke the private bot deployment workflow without changing the privacy boundaries of exported bot bundles.

#### Scenario: Wizard dispatches deploy workflow
- **WHEN** the setup wizard triggers deployment for a configured vault and repository
- **THEN** the GitHub Actions workflow MUST export the private bot bundle, upload it to the Oracle VM, activate the release, restart the bot containers, and run the existing smoke checks

#### Scenario: Workflow artifact remains private
- **WHEN** deployment is triggered by the setup wizard
- **THEN** generated bundle archives and workflow artifacts MUST remain private to the repository workflow and MUST NOT be published to public releases, registries, or images

#### Scenario: Workflow cannot be dispatched
- **WHEN** GitHub Actions cannot dispatch the configured workflow
- **THEN** the setup wizard MUST report the missing workflow, missing permission, unpushed branch, or GitHub authentication problem without producing a partial deploy

### Requirement: Repository prerequisites MUST be machine-checkable
The system MUST expose enough diagnostics for the setup wizard to verify that the private repository can build and deploy the bot bundle.

#### Scenario: Check required repository files
- **WHEN** the setup wizard runs repository doctor checks
- **THEN** it MUST verify that required files are present, including vault Markdown needed for bot indexes, `.backet/config.yaml`, `.backet/state/bot-config.yaml`, `.backet/rules/rules.sqlite3` when rules are enabled, deploy assets, and the deploy workflow file

#### Scenario: Check committed setup files
- **WHEN** setup state or runtime config changed locally
- **THEN** the setup wizard MUST warn that GitHub Actions will not see those changes until they are committed and pushed

#### Scenario: Check workflow push permissions
- **WHEN** the repository contains new or changed files under `.github/workflows/`
- **THEN** deployment setup MUST detect whether the user can push workflow files and MUST explain the required GitHub token scope if not

### Requirement: Oracle deployment prerequisites MUST be doctorable before export
The system MUST let guided setup verify Oracle VM deployment prerequisites before running a private bundle export and upload.

#### Scenario: Remote deploy doctor passes
- **WHEN** the Oracle VM has the expected deploy layout, container runtime, activation scripts, and model cache path
- **THEN** the setup wizard MUST mark Oracle deployment prerequisites ready

#### Scenario: Remote deploy doctor fails
- **WHEN** the Oracle VM is missing required runtime components or paths
- **THEN** the setup wizard MUST report the missing prerequisite and MUST NOT trigger a deployment workflow that is expected to fail for that known reason

#### Scenario: Llama model configured
- **WHEN** setup enables local Llama synthesis
- **THEN** remote deploy doctor MUST verify that the configured model path, checksum, compose profile, and optional model-download token configuration are sufficient for the workflow to bootstrap or reuse the VM-local model cache

### Requirement: Hosted runtime MUST not mutate canonical vault or rules state
The bot runtime MUST answer questions from exported bundle data and MUST NOT perform canonical maintenance operations on the hosted VM.

#### Scenario: User asks while hosted bundle is stale
- **WHEN** the bot receives a Discord question after the local vault has changed but before a new bundle is deployed
- **THEN** the bot MUST answer from the currently deployed bundle and MAY report the bundle export timestamp when asked

#### Scenario: Runtime detects stale or missing semantic support
- **WHEN** the runtime cannot produce compatible semantic query embeddings for a bundled index
- **THEN** it MUST degrade according to configured policy or fail closed with a diagnostic instead of rebuilding embeddings on the VM

#### Scenario: Hosted bot receives maintenance request
- **WHEN** a Discord user asks the hosted bot to ingest PDFs, repair OCR, rewrite notes, or rebuild indexes
- **THEN** the bot MUST refuse and direct the Storyteller to run local Backet maintenance and redeploy a new bundle

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

