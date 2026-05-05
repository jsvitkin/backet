## Context

Backet currently has three local information surfaces that matter for a Discord bot:

- vault context retrieval in `.backet/state/vault-index.sqlite3`
- derived memory under `.backet/memory/`
- ingested rules state under `.backet/rules/rules.sqlite3`

The existing CLI assumes a trusted local operator. A Discord bot changes that trust boundary because several people can ask questions through the same interface, and some of those people must not see Storyteller-only canon. The bot therefore needs access-aware data preparation, permission checks before retrieval, and private response defaults.

The hosting target for the first slice is a private Oracle Cloud Always Free VM. The runtime should be a containerized worker that connects outbound to Discord Gateway, reads a prepared read-only bundle, and optionally calls a local Llama-family model service. The hosted runtime should not need the full repository checkout, source PDFs, Obsidian desktop state, OCR tools, or write access to the canonical vault.

High-level shape:

```text
local machine or manual GitHub Action
  |
  |  backet bot export
  v
bot bundle
  manifest.json
  access-policy.json
  indexes/
    player-vault-index.sqlite3
    storyteller-vault-index.sqlite3
  rules/
    rules.sqlite3
  deploy/
    docker-compose.yml
    env.example
    smoke-test metadata
  |
  |  upload to private VM
  v
Oracle Always Free VM
  |
  +-- backet-bot worker
  |     Discord Gateway, command handling, permission gate, retrieval, answer orchestration
  |
  +-- llama service, optional
        local text synthesis from already-authorized retrieved context
```

## Goals / Non-Goals

**Goals:**

- Provide a private Discord bot for the user's own guild, not a public bot distribution.
- Support player-safe rules and public-canon questions while preserving Storyteller access to hidden canon, plotlines, NPC details, and full rule context.
- Make the security boundary data-first: unauthorized content is excluded from the retrieval corpus before query time.
- Export only the artifacts the hosted bot needs, with source PDFs and machine-specific scratch state left out.
- Run on a free Oracle VM with a private Docker Compose deployment and outbound Discord Gateway connectivity.
- Include local Llama-family synthesis as an optional answer generator with deterministic fallback.
- Keep all bot answers bounded, source-grounded, and citation-bearing.
- Preserve deterministic JSON/agent-facing CLI output for export, diagnostics, and deploy automation.

**Non-Goals:**

- No public marketplace bot, public Docker image containing private data, or multi-tenant service.
- No public HTTP interaction endpoint for the first slice.
- No runtime PDF ingestion, OCR repair, rules reindexing, or vault authoring on the VM.
- No remote model API in the default deployment.
- No model-based permission decisions or post-retrieval redaction as the primary safety mechanism.
- No Discord free-form message monitoring or privileged message-content intent requirement.

## Decisions

### 1. Use Discord Gateway and guild-scoped slash commands

The bot should run as a long-lived worker process that connects outbound to Discord Gateway and registers guild-scoped slash commands for the user's server.

Likely command surface:

```text
/rules ask <question> [private]
/canon ask <question> [private]
/st ask <question>
/st npc <question>
/st plot <question>
/bot sources <last-answer-id>
/bot health
```

Player-safe commands can be available in designated player channels. Storyteller commands require configured Discord role or user IDs and should default to ephemeral/private responses.

Why:

- Gateway avoids a public HTTPS interactions endpoint.
- Slash commands avoid reliance on Discord message-content intent.
- Guild-scoped commands are easier and safer to iterate than global commands.

Alternative considered:

- Public HTTP interaction endpoint. Rejected for the first slice because the user prefers private access and the bot does not need inbound public traffic.
- Chat-message prefix commands. Rejected because they require broader message reading and are harder to permission and audit cleanly.

### 2. Package a read-only bot bundle instead of hosting the whole vault workflow

Add an export operation that assembles a deployment bundle from local Backet state. The hosted runtime should read the bundle and answer questions, not maintain the source corpus.

Bundle contents:

```text
bot-data/
  manifest.json
  access-policy.json
  indexes/
    player-vault-index.sqlite3
    storyteller-vault-index.sqlite3
  rules/
    rules.sqlite3
  model/
    model-manifest.json              optional, not necessarily the GGUF itself
  deploy/
    docker-compose.yml
    systemd/backet-bot.service       optional helper
    env.example
```

The bundle manifest should include:

- Backet CLI version
- bundle schema version
- vault fingerprint or source revision
- export timestamp
- access policy hash
- index backend/model metadata
- rules DB schema/version metadata
- allowed guild ID
- command configuration summary
- whether local answer synthesis is enabled or expected

Why:

- Oracle VM deployment becomes small and predictable.
- The source PDFs remain external and local.
- The bot can be redeployed from a known snapshot during prep without letting runtime mutations drift from the vault.

Alternative considered:

- Mount or sync the live Obsidian vault to the VM and run normal Backet commands there. Rejected because it widens the secret/canon surface, requires more tools on the VM, and makes runtime repair/indexing a production concern.

### 3. Make vault visibility explicit and default-deny for players

Use explicit note frontmatter as the canonical visibility mechanism in v1. Existing unclassified notes should be Storyteller-only for player exports. Do not use folder/path policy as an implicit player-visibility source in the first slice.

Suggested frontmatter:

```yaml
---
backet:
  visibility: player
  bot_topics:
    - canon
---
```

```yaml
---
backet:
  visibility: storyteller
  bot_topics:
    - npc
    - plotline
    - statblock
---
```

The user should not need to hand-edit every note. Add CLI commands that write or update note frontmatter directly:

```text
backet bot visibility audit <vault>
backet bot visibility list <vault> --visibility player
backet bot visibility set <vault> "Player Facing/Domain Primer.md" --visibility player --topic canon
backet bot visibility set <vault> "Player Facing" --visibility player --topic canon --recursive
backet bot visibility set <vault> "11. Plotlines" --visibility storyteller --topic plotline --recursive
backet bot visibility set <vault> "Private Scratch.md" --visibility excluded
backet bot visibility clear <vault> "Drafts/Maybe Later.md"
```

These commands perform bulk metadata updates, but the resulting source of truth is still explicit note metadata on each affected Markdown file. Recursive commands should support dry-run output and should refuse to update ignored or unsafe paths unless explicitly confirmed.

Commit-safe bot configuration can still describe Discord command policy, role mappings, default response visibility, and topic access. That configuration should not classify note visibility by path.

Visibility precedence:

1. built-in safety exclusions such as `.backet/` always win
2. explicit bot exclusion wins over all bot export targets
3. explicit note visibility metadata controls the note's bot scope
4. unclassified notes use `storyteller` for player export safety

Why:

- Explicit metadata keeps player-visible canon reviewable in the vault itself.
- CLI bulk commands keep migration manageable without hiding visibility behind path policy.
- Default-deny prevents accidental player leaks from legacy notes.

Alternative considered:

- Rely only on `.backetignore`. Rejected because `.backetignore` is corpus-wide and cannot express player-safe versus Storyteller-only bot views.
- Rely only on Discord permissions. Rejected because the bot must not retrieve hidden content for unauthorized users at all.
- Use path policy to mark whole folders as player-visible. Rejected for v1 because implicit folder visibility is too easy to forget during later note moves or refactors; recursive CLI commands can still apply explicit metadata to whole folders when that is what the user intends.

### 4. Build separate access-scoped indexes

Bot export should build at least two vault indexes:

```text
player-vault-index.sqlite3
  only player-visible notes

storyteller-vault-index.sqlite3
  all bot-eligible notes, including Storyteller-only notes
```

Additional indexes can be added later if there are semi-private player groups, coterie secrets, or character-specific access rules. The first slice should avoid overfitting that matrix.

Retrieval flow:

```text
Discord user
  -> resolve access tier
  -> select allowed corpus
  -> run exact and semantic query against selected index
  -> optionally query rules
  -> pass only selected sources to answer composer
```

Why:

- It is easier to test absence of hidden content in a player index than to prove every query path redacts correctly.
- Existing retrieval code can remain bounded and source-oriented while export chooses which DB is used.

Alternative considered:

- Single index with per-row access filters. Deferred because it is easier to leak through a missed filter, though it may become useful later for many access groups.

### 5. Keep rules retrieval local, source-based, and scope-aware

The bot bundle should include one shared `.backet/rules/rules.sqlite3` for all bot tiers in v1. Source PDFs stay out of the bundle. The bot may query rules through existing rules retrieval semantics, including exact search, semantic search when embeddings are available, scope assertions, supplement precedence, ambiguity behavior, extraction-quality penalties, and source metadata.

Player rules access should not imply access to hidden chronicle canon. Rule answers for players should use the shared rules corpus and player-visible canon only. Storyteller rules answers can combine the same shared rules corpus with hidden canon if the command/tier allows it.

Why:

- The existing rules store already contains the needed private extracted corpus.
- The user explicitly wants one shared rules SQLite corpus for v1 rather than access-scoped rules exports.
- Shipping source PDFs to the VM would create needless licensing and security risk.
- Rule chunks need citations and bounded excerpts, not full PDF context.

Alternative considered:

- Create separate player and Storyteller rules databases. Rejected for v1 because the user wants a shared rules corpus and the privacy problem is primarily vault canon. If homebrew or unpublished rule material later becomes sensitive, a new change can add access-scoped rules exports.

### 6. Treat local Llama as an answer synthesizer, not an authority

Add an answer generation abstraction with at least two implementations:

```text
template
  deterministic compact answer from sources and snippets

llama-local
  calls a local llama.cpp compatible service with a bounded prompt
```

Default behavior:

- Player-facing commands can use Llama only after permission-gated retrieval.
- Storyteller commands can use Llama with the Storyteller corpus.
- If Llama times out, errors, or is disabled, the bot falls back to template answers.
- If retrieval returns insufficient permitted sources, the bot refuses instead of asking the model to improvise.
- The model prompt must instruct the model to answer only from provided sources and to say when sources are insufficient.

Recommended first model targets:

```text
default: Llama-3.2-3B-Instruct GGUF Q4
stronger optional: Llama-3.1-8B-Instruct GGUF Q4 if VM resources and latency are acceptable
```

Why:

- The model improves phrasing and synthesis, but retrieval decides what evidence exists.
- A smaller quantized model is more realistic on a free CPU VM.
- Template fallback keeps the bot useful without model setup.

Alternative considered:

- Remote LLM API. Deferred because the default deployment should not send private vault/rules snippets off the VM.
- Llama-only answers. Rejected because failures and hallucinations need a deterministic fallback.

### 7. Keep Llama model files in a VM-local deployment cache

Backet should not commit, bundle, or directly own large GGUF model files. Docker Compose should mount a VM-local model directory, and the GitHub Actions deploy flow should run a VM-side bootstrap/download script when the configured model is missing or has the wrong checksum.

Recommended layout:

```text
/srv/backet-bot/
  models/
    llama-3.2-3b-instruct-q4/
      model.gguf
      model.sha256
```

Backet's responsibilities:

- write model expectations into the bundle manifest
- provide deploy templates and a VM-side bootstrap script
- validate that the configured model path/checksum exists during smoke checks
- keep model files out of default bot bundles and committed source

Docker Compose's responsibilities:

- mount `/srv/backet-bot/models` read-only into the `llama` service
- start or omit the `llama` profile according to answer mode

GitHub Actions deploy responsibilities:

- call the VM bootstrap script after uploading the new bundle
- pass any required model-download token as a GitHub secret or leave it configured on the VM
- avoid uploading model files through GitHub artifacts by default

Why:

- GGUF files are large and do not belong in vault commits or bot bundles.
- The VM can cache a model across many bot bundle deployments.
- The model lifecycle is infrastructure-local, while Backet still validates compatibility.

Alternative considered:

- Bundle model files inside every deploy artifact. Rejected because bundles become huge and private data deploys get slower.
- Have Backet download models during normal bot export. Rejected because local export should not require model-download credentials or network access.
- Rely only on an operator-run manual download. Rejected because the user wants the final deploy to be automated through GitHub Actions; the bootstrap script keeps it repeatable.

### 8. Keep embedding/runtime model requirements explicit

Semantic retrieval stores chunk embeddings, but incoming Discord questions still need query embeddings from the same backend/model. Bot export and bot doctor should detect whether the runtime needs:

- Sentence Transformers or another configured embedding backend for semantic queries
- hash embedding fallback
- exact-only fallback

The bundle manifest should identify the embedding backend/model used to build each index and rules DB. The runtime should refuse or degrade clearly when it cannot produce compatible query embeddings.

Why:

- A copied SQLite DB is not enough for semantic query unless the runtime can embed the query compatibly.
- Free VM capacity may require choosing a lighter backend or accepting exact-only behavior.

Alternative considered:

- Always rebuild embeddings on the VM. Rejected because the hosted bot runtime should not own indexing.

### 9. Store bot configuration separately from secrets

Commit-safe configuration can live in the vault or bundle:

```yaml
guild_id: "..."
commands:
  rules:
    min_tier: player
  canon:
    min_tier: player
  st:
    min_tier: storyteller
response_defaults:
  player_public: false
  storyteller_ephemeral: true
```

Secrets must stay outside the vault and repo:

- Discord bot token
- VM SSH key or deploy token
- optional Hugging Face access token for model download
- any remote model API key if a later non-default mode allows one

Why:

- Guild/role IDs are configuration; tokens are secrets.
- Export and deploy can be repeated without baking secrets into private data bundles.

Alternative considered:

- Put all bot config in environment variables. Rejected because role/channel command policy benefits from versioned review with the vault.

### 10. Make Oracle VM deployment boring and replaceable

The first deployment target should be Docker Compose on an Oracle Always Free VM:

```text
/srv/backet-bot/
  docker-compose.yml
  .env                         secrets, not committed
  data/current/                current exported bot bundle
  data/releases/<timestamp>/   optional previous bundles for rollback
  models/                      optional GGUF files
```

Suggested services:

```text
backet-bot
  image: private or locally built bot runtime image
  volumes:
    - ./data/current:/app/data:ro
  env:
    - DISCORD_TOKEN
    - BACKET_BOT_DATA=/app/data
    - BACKET_ANSWER_MODE=template|llama-local

llama
  image: llama.cpp compatible server image
  volumes:
    - ./models:/models:ro
  optional profile: llama
```

Deploy flow:

```text
manual GitHub Actions workflow_dispatch
  -> check out private vault/deploy repo
  -> install Backet
  -> run backet bot export <vault> --output dist/bot-data.tar.zst
  -> upload bundle to Oracle VM over SSH
  -> run VM activation script
       unpack release
       update data/current symlink
       run model bootstrap if llama-local is enabled
       docker compose pull/build/up -d
       run smoke check
```

The GitHub repository that owns the deploy workflow must be private and must contain or fetch:

- the Obsidian vault Markdown needed to build access-scoped indexes
- `.backet/config.yaml`
- `.backet/rules/rules.sqlite3` when rules are enabled
- committed bot configuration for guild ID, command policy, role/channel IDs, response defaults, and model expectations
- note frontmatter visibility metadata for player-visible, Storyteller-only, and bot-excluded notes
- the workflow file and deploy scripts/templates

The repository must not contain:

- Discord bot token
- Oracle VM SSH private key
- Hugging Face or model-download token
- source PDFs unless the private vault repo already intentionally stores them outside bot deployment
- exported bot bundle artifacts from previous runs unless the user explicitly chooses to version private deploy snapshots

Required GitHub Actions secrets/variables should be documented, likely including:

```text
OCI_BOT_HOST
OCI_BOT_USER
OCI_BOT_SSH_KEY
DISCORD_TOKEN
MODEL_DOWNLOAD_TOKEN       optional
BACKET_VAULT_PATH          variable or workflow input
```

Why:

- Oracle VM gives an always-on worker environment with local disk.
- A release directory layout makes rollback a symlink/container restart rather than a rebuild.
- Docker Compose is easier to inspect and repair than a custom orchestration layer.
- GitHub Actions gives a one-button deploy path without Backet owning SSH upload behavior or requiring manual VM commands for every update.

Alternative considered:

- Heroku/container PaaS. Rejected for the first target because ephemeral filesystems and always-on worker costs complicate private corpus hosting.
- Cloud Run/Workers. Rejected for the first target because Gateway workers and local SQLite/model files fit VM hosting better.
- `backet bot deploy` performing SSH upload directly from a local machine. Deferred because the user prefers GitHub Actions as the final deploy mechanism, and CI can keep deployment repeatable once repository prerequisites and secrets are documented.

### 11. Keep terminal UX and JSON contracts separate

Human commands should be concise:

```text
backet bot export ~/Vault
  Exported private bot bundle
  Player notes: 18
  Storyteller notes: 97
  Rules chunks: 1240
  Llama: configured, model not bundled
  Output: dist/backet-bot-2026-05-04.tar.zst
```

JSON output should include complete deterministic data:

- export manifest
- access policy evaluation summary
- denied/excluded counts by reason
- DB paths and fingerprints
- schema versions
- missing semantic backend/model warnings
- bundle contents
- deployment hints

Why:

- Humans need confidence and warnings.
- Agents and CI need exact machine-readable checks.

Alternative considered:

- Only document local packaging without deploy automation. Rejected because this feature is security-sensitive and needs repeatable export validation plus a one-button deploy path.

### 12. Let skills guide visibility, but keep enforcement in CLI/runtime

Workflow skills can be updated to ask about player visibility when drafting notes and to include the correct frontmatter when the user approves writing canon. The CLI and bot runtime must enforce access policy even if skills are not updated yet.

Why:

- Skills and CLI ship separately in Backet.
- The security boundary cannot depend on prompt instructions.

Alternative considered:

- Make Discord bot setup a skill-only workflow. Rejected because access policy, indexes, export, and runtime checks need deterministic tests.

## Risks / Trade-offs

- [Hidden canon leaks through retrieval] -> Build separate access-scoped indexes and run permission checks before retrieval; test player exports against known hidden fixtures.
- [Unclassified legacy notes are accidentally player-visible] -> Default player export to deny unclassified notes unless explicit frontmatter marks them visible.
- [Model hallucinates or uses training memory] -> Provide only retrieved sources, require source-grounded answers, use refusal behavior, and keep template fallback.
- [Local Llama is too slow on free CPU] -> Default to smaller quantized model, enforce timeouts, and fall back to template answers.
- [Semantic query backend missing on VM] -> Record embedding backend/model in the bundle manifest and degrade to exact-only or fail health checks explicitly.
- [Private rule chunks end up in public artifacts] -> Separate code image from data bundle; document private registries only; never commit exported bot bundles unless the target repo is private and intentionally stores those artifacts.
- [Discord role configuration drifts] -> Include `bot doctor` checks and a `/bot health` command that reports configured guild and role mapping without leaking secret values.
- [GitHub Actions deploy exposes private data] -> Require a private vault/deploy repository, store deploy secrets in repository or environment secrets, avoid public artifacts, and document exactly which private files must be present.
- [Oracle Always Free resources are reclaimed or underprovisioned] -> Keep deploy bundle portable and support home-hosting or another VM by reusing Docker Compose.

## Migration Plan

1. Add vault access policy parsing and reporting without changing existing `backet index` behavior.
2. Add access policy evaluation fixtures and tests against sample vaults with player-visible, Storyteller-only, and bot-excluded notes.
3. Add access-scoped index build/export paths used by `backet bot export`.
4. Add bot bundle manifest, packaging, and deterministic `--json` output.
5. Add a local bot runtime that can load a bundle and answer dry-run queries without Discord.
6. Add Discord Gateway integration and guild-scoped slash command registration.
7. Add template answer mode with citations and refusals.
8. Add optional local Llama service integration and timeout/fallback behavior.
9. Add Docker Compose, Oracle VM deployment docs, GitHub Actions deploy workflow, VM bootstrap scripts, and smoke checks.
10. Update skill guidance for visibility metadata after CLI/runtime enforcement exists.

Rollback:

- Disable the Discord bot token or stop the VM worker to take the bot offline immediately.
- Repoint `/srv/backet-bot/data/current` to the previous exported bundle and restart containers.
- Existing vault notes and rules SQLite remain canonical; bot exports are rebuildable snapshots.
- If access metadata causes problems, use the visibility commands to clear or revise note frontmatter without changing normal local `backet context` behavior.

## Resolved Follow-Up Decisions

- `rules.sqlite3` is shared for all bot tiers in v1; canon access is tiered by vault index, not by separate rules databases.
- The final deployment path is a manual GitHub Actions workflow, not local manual SSH steps and not `backet bot deploy` direct SSH upload in v1.
- Model files are VM-local cached deployment assets managed by Docker Compose plus a VM-side bootstrap script invoked by the GitHub Actions deploy flow; Backet records and validates model expectations but does not bundle GGUF files by default.
- Player-visible canon is controlled by explicit note frontmatter in v1. Path policy must not mark notes as player-visible implicitly; CLI visibility commands provide bulk and recursive metadata updates instead.
