# Hosting Backet Bot

This is the friendly path for getting your private Backet Bot into your Discord server.

The main command is:

```bash
backet bot setup /path/to/vault
```

It tells you what is done, what is missing, and which exact phase to run next.

## Before You Start

You need:

- a Backet-initialized vault
- a private GitHub repository for that vault
- an Oracle Always Free VM reachable over SSH
- GitHub CLI: `gh`
- an SSH client
- a Discord account that can create apps and add bots to your server

Check progress anytime:

```bash
backet bot setup status /path/to/vault
backet bot setup resume /path/to/vault
backet bot setup doctor /path/to/vault
```

## 1. Start The Wizard

```bash
backet bot setup /path/to/vault
```

Backet creates:

```text
.backet/state/bot-setup.yaml
```

This file stores non-secret setup facts, such as app ID, server ID, role IDs, GitHub repo, Oracle host/user, deploy path, and answer mode.

Secrets are never stored there.

## 2. Set Up Discord

Run:

```bash
backet bot setup discord /path/to/vault
```

Backet will tell you to open the Discord Developer Portal and:

- create an application
- add a bot
- keep Message Content Intent off
- use Guild Install
- use the `applications.commands` and `bot` scopes
- install the bot only into your private server

When Discord shows the bot token, pass it through stdin:

```bash
backet bot setup discord /path/to/vault --token-stdin
```

Paste the token and press Enter.

After the bot is installed in your server, run Discord setup again with the IDs you want to lock in:

```bash
backet bot setup discord /path/to/vault \
  --token-stdin \
  --guild-id YOUR_SERVER_ID \
  --player-role-id PLAYER_ROLE_ID \
  --storyteller-role-id STORYTELLER_ROLE_ID \
  --canon-channel-id PLAYER_SAFE_CHANNEL_ID
```

Backet validates the bot token and discovers guilds, roles, and channels through Discord's bot APIs. It does not ask for your Discord password, user token, cookies, or browser session.

## 3. Review Player Visibility

Run:

```bash
backet bot setup visibility /path/to/vault
```

If players should see a folder, mark it explicitly:

```bash
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --dry-run
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --yes
```

Then rerun:

```bash
backet bot setup visibility /path/to/vault
```

Unmarked notes are Storyteller-only. That is intentional.

## 4. Check The Oracle VM

Run:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu
```

If the deploy layout is missing:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu --bootstrap
```

Expected layout:

```text
/srv/backet-bot/
  deploy/
  uploads/
  releases/
  data/
  models/
```

Backet validates SSH, Docker/Compose availability, and the deploy directories. It does not store your SSH private key.

## 5. Connect GitHub

Authenticate GitHub CLI:

```bash
gh auth login
gh auth refresh -h github.com -s repo -s workflow
```

Tell Backet which private repository deploys the bot:

```bash
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO
```

Set secrets through the wizard:

```bash
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO --discord-token-stdin
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO --oracle-ssh-key-stdin
```

Required GitHub secrets:

- `DISCORD_TOKEN`
- `ORACLE_VM_SSH_KEY`

Optional GitHub secret:

- `MODEL_DOWNLOAD_TOKEN`

GitHub variables Backet can configure:

- `DISCORD_GUILD_ID`
- `ORACLE_VM_HOST`
- `ORACLE_VM_USER`
- `BOT_COMPOSE_PROFILES`
- `LLAMA_MODEL_RELATIVE_PATH`
- `LLAMA_MODEL_SHA256`
- `LLAMA_MODEL_URL`

The repository needs:

- your bot-visible vault Markdown
- `.backet/config.yaml`
- `.backet/state/bot-setup.yaml`
- `.backet/state/bot-config.yaml`
- `.backet/rules/rules.sqlite3` if rules answers are enabled
- note visibility metadata
- `deploy/bot/*`
- `.github/workflows/deploy-backet-bot.yml`

## 6. Commit And Push

Before deploying, commit and push:

- `.backet/state/bot-setup.yaml`
- `.backet/state/bot-config.yaml`
- visibility metadata changes
- rules SQLite state if needed
- deploy assets and workflow files

GitHub Actions can only deploy what exists in the repository.

## 7. Deploy

Run:

```bash
backet bot setup deploy /path/to/vault --vault-path . --watch
```

Backet dispatches the private GitHub Actions workflow. The workflow exports the bundle, uploads it to the Oracle VM, activates the release, restarts containers, and smoke-checks the bot.

## Safe Example Transcript

The status output is intentionally paste-safe:

```text
Backet bot setup status
phases:
  discord: done
  visibility: done
  oracle: done
  github: needs_action
github:
  secrets:
    DISCORD_TOKEN: configured
    ORACLE_VM_SSH_KEY: missing
  variables:
    DISCORD_GUILD_ID: configured
    ORACLE_VM_HOST: configured
next_phase: github
```

Tokens, private keys, and model download tokens are not printed.

## Day-To-Day Redeploy

When canon or rules change:

```bash
backet bot setup visibility /path/to/vault
git add .
git commit -m "Update bot canon"
git push
backet bot setup deploy /path/to/vault --vault-path . --watch
```

## Troubleshooting

Discord setup pending:

- install the bot into the server
- rerun Discord setup with `--token-stdin`
- choose guild, role, and channel IDs

GitHub setup pending:

- run `gh auth status`
- run `gh auth refresh -h github.com -s repo -s workflow`
- set missing secrets through `--discord-token-stdin` or `--oracle-ssh-key-stdin`

Oracle setup pending:

- check SSH connectivity
- rerun with `--bootstrap`
- make sure Docker and Docker Compose work

Player answers are empty:

- mark player-facing notes with `backet bot visibility set`
- rerun visibility setup
- redeploy

Llama is slow:

- use template mode
- use a smaller Q4 GGUF model
- keep template fallback enabled
