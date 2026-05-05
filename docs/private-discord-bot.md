# Private Discord Bot

For a shorter setup checklist that can be pasted into GitHub Wiki, see [Hosting Backet Bot](wiki/Hosting-Backet-Bot.md).

Backet can export a private, read-only Discord bot bundle for one Storyteller-controlled guild. The hosted bot reads only the exported bundle and does not need the full Obsidian vault, source PDFs, OCR scratch state, or write access to canon.

## Data Shape

The export command writes a bundle such as:

```text
bot-data/
  manifest.json
  access-policy.json
  indexes/
    player-vault-index.sqlite3
    storyteller-vault-index.sqlite3
  rules/
    rules.sqlite3
```

Player queries use the player index. Storyteller commands use the Storyteller index after role or user authorization. The shared `rules.sqlite3` is copied when present; source PDFs are not copied.

## Visibility Metadata

Notes are visible to players only when explicitly marked:

```yaml
---
backet:
  visibility: player
  bot_topics:
    - canon
---
```

Storyteller-only notes use:

```yaml
---
backet:
  visibility: storyteller
  bot_topics:
    - npc
    - plotline
---
```

Bot-excluded notes use `visibility: excluded`. Unmarked notes default to Storyteller-only for player safety.

Useful commands:

```bash
backet bot visibility audit /path/to/vault
backet bot visibility list /path/to/vault --visibility player
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --dry-run
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --yes
backet bot visibility clear /path/to/vault "Drafts/Maybe.md"
```

## Local Export And Dry Run

```bash
backet bot export /path/to/vault --output dist/bot-data --force
backet bot doctor dist/bot-data
backet bot ask dist/bot-data "What are Elysium customs?" --command canon.ask --role-id player-role
```

`backet bot ask` never connects to Discord. It exercises the same bundle runtime and permission path used by the hosted bot.

## Discord Setup

In the Discord Developer Portal:

1. Create an application and bot.
2. Invite it only to your private server with the `bot` and `applications.commands` scopes.
3. Keep Message Content Intent disabled; Backet uses slash command options.
4. Record the guild ID and the relevant role IDs.
5. Store the bot token as a secret, never in the repository.

Guild commands are registered for `/rules`, `/canon`, `/st`, and `/bot`. Storyteller commands default to private interaction responses. Player commands default to private unless the command policy explicitly allows public replies.

Commit-safe bot config lives at `.backet/state/bot-config.yaml`:

```yaml
schema_version: 1
guild_id: "123456789012345678"
roles:
  player:
    - "234567890123456789"
  storyteller:
    - "345678901234567890"
commands:
  canon:
    min_tier: player
    topics: [canon]
    channel_ids: ["456789012345678901"]
    public_allowed: false
answer_mode: template
```

## Local Llama

Template answers are the default. To use a VM-local llama.cpp-compatible service:

```yaml
answer_mode: llama-local
model:
  endpoint: http://llama:8080/completion
  timeout_seconds: 20
  token_budget: 900
  fallback: template
  path: llama-3.2-3b-instruct-q4/model.gguf
  sha256: "<sha256>"
```

Recommended first model: Llama 3.2 3B Instruct GGUF Q4. A Llama 3.1 8B Instruct Q4 model may work if the VM has enough memory and you can tolerate slower answers. Model files are VM-local cache assets and are not committed or bundled.

The deployment assumes a small CPU-only Always Free style VM. Expect template answers to be immediate, 3B Q4 local Llama answers to be usable but not snappy, and 8B Q4 answers to be noticeably slower or memory-sensitive. Keep `fallback: template` enabled so the bot remains useful when inference is slow.

## Oracle VM Layout

The deploy assets assume:

```text
/srv/backet-bot/
  deploy/
    docker-compose.yml
    .env
    activate-release.sh
    bootstrap-llama-model.sh
  uploads/
  releases/
    run-123/
  data/
    current -> /srv/backet-bot/releases/run-123
  models/
    llama-3.2-3b-instruct-q4/model.gguf
```

Activation unpacks a release, validates it, updates `data/current`, bootstraps the model cache if configured, restarts Compose, and runs an inspect smoke check. Rollback is changing `data/current` back to an older release directory and restarting Compose.

## Manual GitHub Actions Deploy

The workflow at `.github/workflows/deploy-backet-bot.yml` is manual-only. It exports the bundle from a private repository, uploads the private artifact to the VM, writes the VM `.env` from GitHub secrets and variables, activates the release, bootstraps VM-local models when configured, and restarts the containers.

Required private repository contents:

- Vault Markdown needed for bot indexes
- `.backet/config.yaml`
- `.backet/state/bot-config.yaml`
- `.backet/rules/rules.sqlite3` when rules are enabled
- Explicit note visibility frontmatter
- `deploy/bot/*`
- `.github/workflows/deploy-backet-bot.yml`

Required GitHub secrets:

- `ORACLE_VM_HOST`
- `ORACLE_VM_USER`
- `ORACLE_VM_SSH_KEY`
- `DISCORD_TOKEN`
- `MODEL_DOWNLOAD_TOKEN` when the model URL requires one

Useful GitHub variables:

- `DISCORD_GUILD_ID`
- `BOT_COMPOSE_PROFILES`, set to `llama` when using local Llama
- `LLAMA_MODEL_RELATIVE_PATH`
- `LLAMA_MODEL_SHA256`
- `LLAMA_MODEL_URL`

Never publish the bot bundle to a public release, package registry, or public container image. The code image may be public, but vault notes, extracted rules chunks, bot bundles, `.env`, tokens, keys, source PDFs, and GGUF model files stay private.

## Troubleshooting

- Missing player-visible notes: run `backet bot visibility audit` and mark approved notes explicitly.
- Incompatible bundle: run `backet bot doctor <bundle>` and redeploy after export.
- Missing semantic backend: the runtime falls back or fails according to answer/retrieval mode; install the matching retrieval dependency or use exact/template behavior.
- Discord token errors: rotate the token in the Developer Portal and update the GitHub or VM secret.
- Slow Llama answers: use template mode, a smaller GGUF, a shorter token budget, or a longer timeout.
