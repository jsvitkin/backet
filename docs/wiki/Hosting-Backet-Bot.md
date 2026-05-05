# Hosting Backet Bot

This guide gets Backet Bot from your local/private vault into your Discord server.

Backet Bot is private by design. You do not publish the bot, the rules database, source PDFs, or your vault. You export only the runtime bundle the bot needs, then deploy it to your Oracle Always Free VM.

## What You Need

- A private GitHub repository containing the vault files needed for bot export.
- Your committed `.backet/rules/rules.sqlite3` if you want rules answers.
- Player-safe notes explicitly marked with `backet.visibility: player`.
- An Oracle Always Free VM with Docker and Docker Compose installed.
- A Discord application/bot token for your private server.
- Optional: a VM-local Llama GGUF model if you want synthesized answers.

## One-Time Discord Setup

1. Open the Discord Developer Portal.
2. Create an application and add a bot user.
3. Invite it only to your private server.
4. Use the `bot` and `applications.commands` scopes.
5. Keep Message Content Intent off; Backet uses slash command options.
6. Save these IDs:
   - Discord guild/server ID
   - player role ID
   - Storyteller role ID
   - any allowed channel IDs
7. Store the bot token as a GitHub secret named `DISCORD_TOKEN`.

## One-Time Vault Setup

Create `.backet/state/bot-config.yaml`:

```yaml
schema_version: 1
guild_id: "your-discord-server-id"
roles:
  player:
    - "player-role-id"
  storyteller:
    - "storyteller-role-id"
commands:
  canon:
    min_tier: player
    topics: [canon]
    channel_ids: ["allowed-player-channel-id"]
    public_allowed: false
answer_mode: template
```

Mark player-visible notes explicitly:

```bash
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --dry-run
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --yes
```

Check what players can see:

```bash
backet bot visibility audit /path/to/vault
backet bot visibility list /path/to/vault --visibility player
```

Unmarked notes are Storyteller-only for player safety.

## Test Locally Before Hosting

Export a bundle:

```bash
backet bot export /path/to/vault --output dist/bot-data --force
backet bot doctor dist/bot-data
```

Try a player-safe question without Discord:

```bash
backet bot ask dist/bot-data "What does the court know about Elysium?" --command canon.ask --role-id player-role-id
```

Try a Storyteller question:

```bash
backet bot ask dist/bot-data "What is Sabine hiding?" --command st.npc --role-id storyteller-role-id
```

If a player asks a Storyteller command, the bot should deny before opening hidden indexes.

## Oracle VM Layout

Create this layout on the VM:

```text
/srv/backet-bot/
  deploy/
  uploads/
  releases/
  data/
    current -> /srv/backet-bot/releases/latest-release
  models/
```

The deploy workflow uploads:

- `docker-compose.yml`
- `.env`
- activation scripts
- the private bundle archive

The bot runs from `/srv/backet-bot/data/current`.

## GitHub Actions Setup

Use the included workflow:

```text
.github/workflows/deploy-backet-bot.yml
```

Required GitHub secrets:

- `ORACLE_VM_HOST`
- `ORACLE_VM_USER`
- `ORACLE_VM_SSH_KEY`
- `DISCORD_TOKEN`
- `MODEL_DOWNLOAD_TOKEN` only if your model download needs one

Recommended GitHub variables:

- `DISCORD_GUILD_ID`
- `BOT_COMPOSE_PROFILES`, set to `llama` only when using local Llama
- `LLAMA_MODEL_RELATIVE_PATH`
- `LLAMA_MODEL_SHA256`
- `LLAMA_MODEL_URL`

To deploy:

1. Push your vault, rules database, bot config, and visibility metadata to the private repo.
2. Open GitHub Actions.
3. Run `Deploy private Backet bot`.
4. Set `vault_path` to the vault path inside the repo, usually `.`.
5. Wait for export, upload, activation, restart, and smoke checks.

## Optional Llama Setup

Template answers work without a model. For local Llama, add this to `bot-config.yaml`:

```yaml
answer_mode: llama-local
model:
  endpoint: http://llama:8080/completion
  timeout_seconds: 20
  token_budget: 900
  fallback: template
  path: llama-3.2-3b-instruct-q4/model.gguf
  sha256: "expected-model-sha256"
```

Use a small quantized model first, such as Llama 3.2 3B Instruct Q4. The model file lives on the VM under `/srv/backet-bot/models`; it is not committed and not included in bot bundles.

## Day-To-Day Redeploy

When you change canon or rules:

1. Update notes locally.
2. Make sure new player-facing notes have visibility metadata.
3. Commit and push to the private repo.
4. Run the manual GitHub Actions deploy again.

The hosted bot answers from the currently deployed bundle until you redeploy.

## Rollback

On the VM, point `data/current` at an older release and restart Compose:

```bash
sudo ln -sfn /srv/backet-bot/releases/older-release /srv/backet-bot/data/current
cd /srv/backet-bot/deploy
sudo docker compose up -d
```

## Common Problems

No player-visible notes:

```bash
backet bot visibility audit /path/to/vault
```

Then mark approved notes with `backet bot visibility set`.

Bundle fails doctor:

```bash
backet bot doctor dist/bot-data
```

Re-export after fixing the reported file or schema issue.

Discord token error:

- Rotate the token in the Discord Developer Portal.
- Update the `DISCORD_TOKEN` GitHub secret or VM `.env`.

Llama is too slow:

- Use `answer_mode: template`.
- Try a smaller Q4 model.
- Lower `token_budget`.
- Keep `fallback: template` enabled.

Player sees too little:

- The note is probably unmarked or missing the right topic.
- Run `backet bot visibility list /path/to/vault --visibility player`.

Player sees too much:

- Change the note to `visibility: storyteller` or `visibility: excluded`.
- Redeploy immediately.
