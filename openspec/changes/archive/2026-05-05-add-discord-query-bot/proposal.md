## Why

Backet already has bounded vault retrieval and private rules retrieval, but those capabilities are available only through local CLI and agent workflows. A private Discord bot would let players ask safe rules or public-canon questions during play while letting the Storyteller query hidden canon, plotlines, NPC details, and rules context without exposing private material in public channels.

This needs a proposal now because Discord access changes the safety model: player-safe answers require visibility-aware vault data, role-gated bot commands, private response behavior, and a deployable read-only data bundle rather than simply wrapping the existing CLI in chat.

## What Changes

- Add a private Discord Gateway bot for one Storyteller-controlled Discord server, with guild-scoped slash commands rather than a publicly downloadable or broadly installable bot.
- Add role, user, and channel aware permission checks before retrieval so players can query player-safe rules and canon while Storyteller-only queries can reach hidden canon, plotlines, NPCs, stat blocks, and full rules context.
- Add vault access policy conventions so Obsidian notes can be classified as player-visible, Storyteller-only, or excluded from bot export through explicit frontmatter metadata, with CLI commands to audit and bulk-apply that metadata.
- Add access-scoped vault indexing/export behavior so player queries search only player-safe canon and Storyteller queries search the broader authorized corpus; unauthorized content must never be retrieved and then redacted after the fact.
- Add a deployable bot data bundle that contains only the runtime artifacts needed by the bot, such as filtered SQLite indexes, shared rules SQLite state, access policy, and manifest metadata.
- Target Oracle Cloud Always Free VM deployment for the first hosted runtime, using a private Docker Compose deployment with outbound Discord Gateway access and no public HTTP interactions endpoint.
- Add local Llama-family answer synthesis as an optional runtime service for source-grounded Discord-sized answers, with deterministic/template fallback when model inference is unavailable, too slow, or not enabled.
- Keep answer generation source-grounded: the bot should cite retrieved vault notes and rule sources, refuse when permitted context is insufficient, and avoid using model memory as authority.
- Support a manual GitHub Actions packaging/deploy flow that runs export, uploads the bundle to the private VM, activates the release, refreshes VM-local model files when needed, and restarts the bot.
- Keep source PDFs outside the bot bundle; the bundle may contain the private ingested rules SQLite corpus but must not require or copy original PDFs.

### Non-Goals

- Do not publish a general-purpose Discord bot, public bot package, public Docker image containing private data, or public marketplace integration.
- Do not expose a public Discord interactions webhook endpoint in the initial slice; prefer Gateway because the bot only needs outbound access to Discord.
- Do not support multi-tenant hosting, arbitrary third-party servers, or self-service bot installation by other groups.
- Do not ingest rule PDFs, repair OCR, rebuild rules chunks, or author canon inside the hosted bot runtime.
- Do not make Llama or any model responsible for deciding permissions, widening retrieval scope, or answering from hidden data for unauthorized users.
- Do not send vault canon, rules chunks, or Discord questions to remote model APIs in the default private deployment.
- Do not load the entire vault, an entire section, or whole rulebooks into prompt context.

## Capabilities

### New Capabilities

- `discord-query-bot`: Private Discord Gateway bot behavior, slash commands, permission gating, response visibility, source-grounded refusals, and optional local Llama answer synthesis.
- `bot-deployment-bundles`: Export, package, verify, and deploy read-only bot runtime bundles through a private GitHub Actions to Oracle VM flow without copying source PDFs or machine-specific scratch state.
- `vault-access-policy`: Vault-side visibility metadata and CLI visibility-management commands for classifying player-visible, Storyteller-only, and bot-excluded canon.

### Modified Capabilities

- `vault-indexing`: Add access-scoped indexing and retrieval behavior so player-safe and Storyteller-safe bot indexes are built from the effective visibility policy instead of a single all-canon retrieval corpus.

## Impact

- CLI: likely adds `backet bot export`, `backet bot doctor`, `backet bot visibility ...`, and GitHub Actions deploy-helper generation or validation surfaces, plus access-aware index/export options.
- Bot runtime: adds a long-running private Discord Gateway worker that reads a prepared bundle, handles slash commands, calls Backet retrieval over read-only SQLite data, and optionally calls a VM-local Llama service.
- Vault notes: use `backet.visibility` or similar frontmatter for per-note visibility; existing notes without metadata default to Storyteller-only for player bot export safety.
- Per-vault state: stores committed, portable bot export metadata and filtered indexes under `.backet/` as durable or rebuildable state as appropriate; machine-specific cache, OCR work, model downloads, and deploy credentials remain ignored/outside the vault.
- Rules corpus: the bot bundle includes one shared `.backet/rules/rules.sqlite3` for all bot tiers in v1, with generated embeddings/scope metadata; source PDFs stay external and are not shipped to the VM.
- Dependencies: adds Discord bot runtime dependencies, container/deploy assets, and optional local Llama/llama.cpp integration; Sentence Transformers or the configured embedding backend may still be needed at runtime to embed incoming queries.
- Security: introduces bot tokens, Discord guild/role IDs, VM SSH/deploy credentials, and optional model files; tokens and keys must be secrets, while model files remain VM-local deployment assets rather than committed repo or bundle artifacts.
- Skills: authoring skills may mention player/ST visibility conventions when creating canon, but CLI and bot behavior must not depend on skill updates shipping at the same time.
- Retrieval bounds: all bot answers must be assembled from bounded query results, filtered indexes, and source metadata, never from whole-vault or whole-rulebook prompt loading.
