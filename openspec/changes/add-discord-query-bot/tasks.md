## 1. Access Policy Foundation

- [x] 1.1 Define bot visibility values, topic values, and access tiers in a dedicated access-policy module
- [x] 1.2 Add commit-safe bot configuration parsing for guild ID, command policy, role/channel mapping, response defaults, and model expectations
- [x] 1.3 Add frontmatter extraction for `backet.visibility`, `backet.bot_topics`, and bot exclusion metadata without changing normal note parsing
- [x] 1.4 Implement deterministic policy precedence for built-in exclusions, explicit bot exclusions, explicit note metadata, and unclassified default-deny behavior
- [x] 1.5 Implement frontmatter update helpers that preserve unrelated Obsidian properties and Markdown content
- [x] 1.6 Implement default-deny player behavior for unclassified notes
- [x] 1.7 Add policy decision objects that record metadata source, effective visibility, topics, and exclusion reason for each note
- [x] 1.8 Add human-readable policy audit output with counts by visibility, topic, override, exclusion, and default
- [x] 1.9 Add deterministic JSON policy audit output with per-note decisions
- [x] 1.10 Add validation errors for unsupported visibility values, invalid topics, missing required metadata, and unsafe ambiguous configuration
- [x] 1.11 Add fixtures for player-visible notes, Storyteller-only notes, bot-excluded notes, and unclassified legacy notes
- [x] 1.12 Add tests for access-policy precedence and default-deny behavior
- [x] 1.13 Add tests proving bot-excluded notes remain available to normal local retrieval only when not otherwise ignored
- [x] 1.14 Implement `backet bot visibility audit <vault>` with human and JSON output
- [x] 1.15 Implement `backet bot visibility list <vault>` filters for visibility, topic, and unclassified notes
- [x] 1.16 Implement `backet bot visibility set <vault> <path>` for single-note metadata updates
- [x] 1.17 Implement recursive `backet bot visibility set` for folder targets that writes explicit metadata to each eligible note
- [x] 1.18 Implement `backet bot visibility clear <vault> <path>` for single-note and recursive metadata removal
- [x] 1.19 Add dry-run and confirmation behavior for recursive visibility updates
- [x] 1.20 Add tests for visibility set, clear, list, audit, recursive updates, dry-run behavior, and preservation of unrelated frontmatter

## 2. Access-Scoped Vault Indexing

- [x] 2.1 Add an internal index build path that accepts an explicit set of eligible Markdown paths
- [x] 2.2 Build a player vault index from player-eligible policy decisions during bot export
- [x] 2.3 Build a Storyteller vault index from Storyteller-eligible policy decisions during bot export
- [x] 2.4 Preserve existing exact and semantic indexing behavior inside each access-scoped index
- [x] 2.5 Make access-scoped indexes portable so they do not require the original vault path at runtime
- [x] 2.6 Include access scope, note count, chunk count, content fingerprint, and embedding metadata for each bot index
- [x] 2.7 Detect visibility/topic metadata changes as bot index refresh triggers even when note body content hashes are unchanged
- [x] 2.8 Add tests that hidden plotline content cannot appear in the player index
- [x] 2.9 Add tests that hidden note titles and headings cannot appear in player index metadata
- [x] 2.10 Add tests for player and Storyteller semantic lookup against separate scoped indexes
- [x] 2.11 Add tests for empty player index behavior and warnings
- [x] 2.12 Preserve existing `backet index` and `backet context` behavior outside bot export

## 3. Bot Bundle Export and Diagnostics

- [x] 3.1 Add a `bot` Typer subcommand group to the CLI
- [x] 3.2 Implement `backet bot policy` or equivalent command-configuration inspection command
- [x] 3.3 Implement `backet bot export <vault>` with output directory or archive options
- [x] 3.4 Define and write `manifest.json` with CLI version, bundle schema version, export timestamp, vault fingerprint, policy hash, index metadata, and rules metadata
- [x] 3.5 Copy access-scoped vault indexes into the bundle using stable paths
- [x] 3.6 Copy one shared `rules.sqlite3` into the bundle when rules are enabled and present
- [x] 3.7 Exclude source PDFs from all bundle outputs
- [x] 3.8 Exclude `.backet/cache`, `.backet/temp`, `.backet/ocr-work`, model downloads, deploy credentials, and other machine-specific state
- [x] 3.9 Add bundle integrity checks for missing index files, missing rules DB, unsupported schema versions, and manifest mismatches
- [x] 3.10 Add `backet bot doctor` for local bundle validation before deploy
- [x] 3.11 Add concise human export output with corpus counts, model status, warnings, and output path
- [x] 3.12 Add deterministic JSON export output with policy decisions, file fingerprints, warnings, and deploy hints
- [x] 3.13 Add tests proving bot export fails closed when the access policy is invalid
- [x] 3.14 Add tests proving exported bundles do not contain source PDFs or ignored scratch directories
- [x] 3.15 Add tests for bundle manifest determinism and schema version compatibility

## 4. Runtime Retrieval and Answer Orchestration

- [x] 4.1 Add a bot runtime package or module that can load a bundle without an Obsidian vault path
- [x] 4.2 Implement read-only SQLite opening for player and Storyteller vault indexes
- [x] 4.3 Implement read-only rules DB opening from the bundle
- [x] 4.4 Add access-tier resolution interfaces that can be reused by Discord handlers and dry-run tests
- [x] 4.5 Implement command-to-corpus selection for rules, canon, Storyteller, NPC, plotline, and stat block workflows
- [x] 4.6 Implement source retrieval against the selected access-scoped vault index
- [x] 4.7 Implement rules retrieval from the bundled rules DB while preserving scope assertions, precedence, ambiguity, and diagnostics
- [x] 4.8 Detect incompatible or unavailable query embedding backends and degrade or fail according to configured policy
- [x] 4.9 Add deterministic/template answer composition with citations for vault and rules sources
- [x] 4.10 Implement source-grounded refusal when permitted retrieval is insufficient
- [x] 4.11 Implement response shortening or splitting for Discord content and embed limits
- [x] 4.12 Suppress unintended Discord mentions in all generated content
- [x] 4.13 Add dry-run command tests that exercise retrieval and answer generation without connecting to Discord
- [x] 4.14 Add tests for rule ambiguity surfacing through bot answers
- [x] 4.15 Add tests proving player runtime queries never open or query the Storyteller index

## 5. Discord Gateway Bot

- [x] 5.1 Choose and add the Discord Python dependency behind a suitable optional dependency group
- [x] 5.2 Implement Discord Gateway startup with configured token, guild ID, intents, and fail-closed validation
- [x] 5.3 Register or verify guild-scoped slash commands for `/rules`, `/canon`, `/st`, and `/bot`
- [x] 5.4 Implement role and user mapping from config to player and Storyteller access tiers
- [x] 5.5 Implement player-safe `/rules ask` handling
- [x] 5.6 Implement player-safe `/canon ask` handling
- [x] 5.7 Implement Storyteller-only `/st ask`, `/st npc`, and `/st plot` handling
- [x] 5.8 Implement `/bot sources` or equivalent source-inspection behavior for the user's recent answer
- [x] 5.9 Implement `/bot health` with Storyteller-safe and player-safe output variants
- [x] 5.10 Enforce ephemeral/private defaults for Storyteller answers and permission denials
- [x] 5.11 Enforce channel restrictions and public-answer policy for player commands
- [x] 5.12 Add graceful startup, reconnect, shutdown, and signal handling for the long-running worker
- [x] 5.13 Add sanitized structured logging for command name, access tier, retrieval mode, and result status without logging source text by default
- [x] 5.14 Add tests for permission denial before retrieval
- [x] 5.15 Add tests for guild mismatch and missing role mapping behavior
- [x] 5.16 Add mock Discord integration tests for command routing and response visibility

## 6. Local Llama Answer Synthesis

- [x] 6.1 Define answer generator interfaces for template and local Llama modes
- [x] 6.2 Add configuration for answer mode, model endpoint, timeout, token budget, and fallback behavior
- [x] 6.3 Add a bounded prompt builder that includes only permitted source snippets, source metadata, and the user question
- [x] 6.4 Add prompt instructions requiring source-grounded answers and refusals when sources are insufficient
- [x] 6.5 Implement local llama.cpp-compatible HTTP client support
- [x] 6.6 Implement timeout, error, and malformed-output handling with template fallback
- [x] 6.7 Add output validation for missing citations, unsupported claims, and overlong responses
- [x] 6.8 Add model manifest support for recommended Llama 3.2 3B Q4 and optional Llama 3.1 8B Q4 configurations
- [x] 6.9 Keep GGUF model files outside committed source and outside bot data bundles by default
- [x] 6.10 Add tests with a fake local model service for successful synthesis, timeout fallback, and unsupported-claim fallback
- [x] 6.11 Add tests proving the model client never receives hidden sources for player requests
- [x] 6.12 Add smoke validation that checks VM-local model path and checksum when `llama-local` mode is enabled

## 7. Oracle VM Deployment Assets

- [x] 7.1 Add Dockerfile or runtime image build instructions for the bot worker
- [x] 7.2 Add Docker Compose template for `backet-bot` and optional `llama` services
- [x] 7.3 Add `.env.example` documenting required secrets without real values
- [x] 7.4 Add VM directory layout documentation for `/srv/backet-bot`, `data/current`, release bundles, and model files
- [x] 7.5 Add VM activation script for unpacking an uploaded bundle, relinking `data/current`, restarting containers, and running smoke checks
- [x] 7.6 Add rollback instructions using previous bundle directories
- [x] 7.7 Add smoke-test command or checklist that verifies bundle load, Discord config, index availability, rules availability, and answer mode
- [x] 7.8 Add required manual GitHub Actions workflow template for private bundle build/upload/activate/smoke deploy
- [x] 7.9 Add VM-side model bootstrap script that verifies or downloads configured GGUF models into `/srv/backet-bot/models`
- [x] 7.10 Document required private repository contents for the GitHub Actions deploy workflow
- [x] 7.11 Document required GitHub Actions secrets and variables for Oracle VM SSH, Discord token, optional model token, and vault path
- [x] 7.12 Ensure generated deploy assets never embed Discord tokens, SSH keys, Hugging Face tokens, or private model credentials
- [x] 7.13 Add docs for Oracle Always Free sizing assumptions, expected latency trade-offs, and template fallback when local Llama is slow
- [x] 7.14 Add tests or static checks for workflow templates and deploy scripts to confirm bundles are private artifacts and model files are not uploaded through GitHub artifacts by default

## 8. Documentation and Skill Guidance

- [x] 8.1 Update README with the private Discord bot concept, non-goals, and high-level setup flow
- [x] 8.2 Document vault visibility frontmatter schema, visibility command examples, recursive metadata workflows, and default-deny player behavior
- [x] 8.3 Document bot export, doctor, GitHub Actions deploy, rollback, and redeploy workflows
- [x] 8.4 Document Discord developer setup steps, required scopes, guild command registration, and role/channel mapping
- [x] 8.5 Document local Llama setup, recommended model sizes, timeout behavior, and template fallback
- [x] 8.6 Document what data is safe to commit, what must remain private, what belongs in the private vault/deploy repo, and what should never be published
- [x] 8.7 Update workflow-authoring guidance so future canon-writing skills can ask about player visibility and write frontmatter when approved
- [x] 8.8 Add skill packaging tests ensuring updated skill guidance remains installable and concise
- [x] 8.9 Add troubleshooting guidance for missing semantic backend, incompatible bundle manifest, Discord token errors, and no player-visible notes

## 9. Security, Privacy, and Regression Testing

- [x] 9.1 Add a dedicated leakage fixture containing hidden plotline, hidden NPC, public canon, and overlapping names
- [x] 9.2 Add unit tests proving player policy export excludes hidden content, headings, excerpts, and metadata
- [x] 9.3 Add integration tests proving player bot answers cannot cite hidden sources
- [x] 9.4 Add tests proving permission denials occur before any Storyteller index or rules/canon hidden retrieval
- [x] 9.5 Add tests proving Storyteller commands can retrieve hidden sources when authorized
- [x] 9.6 Add tests proving source PDFs are never copied into bundle archives
- [x] 9.7 Add tests proving secrets are never written to manifests, deploy assets, JSON output, or logs
- [x] 9.8 Add tests for read-only runtime behavior against bundle SQLite files
- [x] 9.9 Add tests for exact-only fallback when semantic query embeddings are unavailable
- [x] 9.10 Add tests for local Llama fallback when the model service is unavailable or too slow
- [x] 9.11 Add CLI contract tests for `backet bot` human output and JSON output
- [x] 9.12 Add install/smoke coverage ensuring the new optional bot dependencies do not break baseline CLI installation
- [x] 9.13 Add CI checks for OpenSpec spec formatting and task completeness
- [x] 9.14 Run the full test suite and update coverage expectations for access policy, export, runtime, and bot modules
