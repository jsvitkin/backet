## ADDED Requirements

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
