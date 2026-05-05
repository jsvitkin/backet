# Private Discord Bot

Backet can run a private Discord bot for one Storyteller-controlled server. The bot is not published, the source PDFs are not copied, and the hosted VM reads only an exported runtime bundle.

The preferred setup path is the guided CLI:

```bash
backet bot setup /path/to/vault
```

In an interactive terminal, that command is a real wizard. It prompts through local deploy files, Discord bot validation and server/role/channel selection, visibility review, answer mode, GitHub secrets/variables, Oracle SSH validation, and deployment. You can stop and resume at any point.

For a menu covering the whole bot command surface:

```bash
backet bot
```

That command guides setup, visibility, policy review, bundle export, bundle doctor/inspect, dry-run questions, model checks, and foreground bot runtime.

For a non-interactive, paste-safe status view:

```bash
backet bot setup --no-guided /path/to/vault
```

## Guided Flow

The main wizard runs these phases in order. The same focused commands remain available for automation or retrying one phase:

```bash
backet bot setup /path/to/vault
backet bot setup files /path/to/vault
backet bot setup discord /path/to/vault
backet bot setup visibility /path/to/vault
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO
backet bot setup deploy /path/to/vault --vault-path .
```

Useful status commands:

```bash
backet bot setup status /path/to/vault
backet bot setup resume /path/to/vault
backet bot setup doctor /path/to/vault
```

The setup wizard writes non-secret facts to:

```text
.backet/state/bot-setup.yaml
```

The bot runtime still reads:

```text
.backet/state/bot-config.yaml
```

Secrets are never written to either file.

If setup reports that the deployment workflow or deploy assets are missing, the interactive wizard asks to install them. You can also run the focused command:

```bash
backet bot setup files /path/to/vault
```

Run this from the private vault repository. If the vault is a subdirectory, pass the repository root explicitly:

```bash
backet bot setup files /path/to/vault --repo-root /path/to/private-repo
```

This writes `.github/workflows/deploy-backet-bot.yml` and `deploy/bot/*`. Existing changed files are not overwritten unless you rerun with `--force-files`.

## Discord Phase

The wizard cannot safely create the Discord application for you, because that would require automating your Discord user account. It guides the browser-only parts and validates the result from the terminal.

The main wizard guides this phase. The focused command is:

```bash
backet bot setup discord /path/to/vault
```

It will point you to the Discord Developer Portal and tell you to:

- create an application
- add a bot user
- keep Message Content Intent disabled
- use Guild Install
- use the `applications.commands` and `bot` scopes
- install the bot only into your private server

In the interactive wizard, paste the bot token into the hidden prompt. For the focused command, pass it through stdin so it does not land in shell history:

```bash
backet bot setup discord /path/to/vault --token-stdin
```

Then paste the token and press Enter. Backet validates it, generates the install URL, discovers the bot's guilds, channels, and roles, and lets you choose the mappings by number in the terminal.

If you already know the server and role IDs:

```bash
backet bot setup discord /path/to/vault \
  --token-stdin \
  --guild-id 123456789012345678 \
  --player-role-id 234567890123456789 \
  --storyteller-role-id 345678901234567890 \
  --canon-channel-id 456789012345678901
```

Backet refuses Discord user tokens, passwords, cookies, and OAuth bearer tokens. It only uses bot-token plus browser-consent flows.

## Visibility Phase

Players see only notes explicitly marked player-visible:

```yaml
---
backet:
  visibility: player
  bot_topics:
    - canon
---
```

The setup wizard runs this review before deployment and can open the visibility editor when notes need classification. You can open the editor directly:

```bash
backet bot visibility
```

The editor audits the vault, lists unclassified notes, previews changes, and asks before writing. The focused audit command is:

```bash
backet bot setup visibility /path/to/vault
```

The wizard summarizes player-visible, Storyteller-only, bot-excluded, unmarked, missing-topic, and rules corpus state. If there are no player-visible notes, deployment is blocked until you either mark notes or confirm that an empty player canon index is intentional:

```bash
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --dry-run
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --yes
backet bot setup visibility /path/to/vault
```

Unmarked notes default to Storyteller-only for player safety.

## GitHub Phase

Backet deploys through the private GitHub Actions workflow. The wizard uses `gh` to configure secrets and variables when available:

```bash
gh auth login
gh auth refresh -h github.com -s repo -s workflow
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO
```

Secret values are sent to GitHub Actions secrets, not written to disk. The wizard prompts for the Discord token and SSH key path. Focused commands can configure them one at a time through stdin:

```bash
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO --discord-token-stdin
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO --oracle-ssh-key-stdin
```

GitHub secrets:

- `DISCORD_TOKEN`
- `ORACLE_VM_SSH_KEY`
- `MODEL_DOWNLOAD_TOKEN` only when your model download URL requires it

GitHub variables:

- `DISCORD_GUILD_ID`
- `ORACLE_VM_HOST`
- `ORACLE_VM_USER`
- `BOT_COMPOSE_PROFILES`
- `LLAMA_MODEL_RELATIVE_PATH`
- `LLAMA_MODEL_SHA256`
- `LLAMA_MODEL_URL`

The workflow also accepts Oracle host/user as secrets if you choose to hide those values, but variables are the default.

Your private repository must contain:

- vault Markdown needed for bot indexes
- `.backet/config.yaml`
- `.backet/state/bot-setup.yaml`
- `.backet/state/bot-config.yaml`
- `.backet/rules/rules.sqlite3` when rules answers are enabled
- explicit note visibility metadata
- `deploy/bot/*`
- `.github/workflows/deploy-backet-bot.yml`

The installed workflow uses the public Backet release wheel plus bot dependencies, so your private vault repository does not need to contain the Backet source code.

## Oracle Phase

V1 assumes you already have an SSH-reachable Oracle Always Free VM. Backet does not create Oracle cloud resources yet.

The wizard asks for the Oracle host, SSH user, deploy path, and local key path for validation. The focused command is:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu
```

To validate with a local key file:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu --ssh-key ~/.ssh/backet_bot_deploy
```

To ask Backet to create/check the remote deploy layout:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu --bootstrap
```

Expected VM layout:

```text
/srv/backet-bot/
  deploy/
  uploads/
  releases/
  data/
  models/
```

The SSH private key value belongs in the GitHub secret `ORACLE_VM_SSH_KEY`, not in `.backet`.

## Deploy Phase

After setup files are committed and pushed, the wizard offers to deploy. The focused command is:

```bash
backet bot setup deploy /path/to/vault --vault-path . --watch
```

The wizard dispatches `.github/workflows/deploy-backet-bot.yml`. GitHub Actions exports the private bundle, uploads it to the VM, activates the release, restarts the containers, and runs the smoke check.

If local setup files are dirty or unpushed, deployment is blocked because GitHub Actions cannot see them yet.

## Local Bundle Reference

You can still export and test manually:

```bash
backet bot export /path/to/vault --output dist/bot-data --force
backet bot doctor dist/bot-data
backet bot ask dist/bot-data "What does the court know about Elysium?" --command canon.ask --role-id player-role
```

The bundle shape is:

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

The bundle does not include source PDFs, model files, tokens, SSH keys, or the full Obsidian vault.

## Optional Local Llama

Template answers are the default and work without a model. For local Llama, configure the runtime model and let the VM cache the GGUF file under `/srv/backet-bot/models`.

Recommended first model: Llama 3.2 3B Instruct GGUF Q4. Keep fallback to template enabled, because Always Free CPU-only resources can be slow.

Model files are VM-local cache assets. They are not committed and not bundled.

## Troubleshooting

### Missing player-visible notes

Run:

```bash
backet bot setup visibility /path/to/vault
```

Then mark approved notes with `backet bot visibility set`. Unmarked notes stay Storyteller-only.

### Incompatible bundle

Run:

```bash
backet bot doctor dist/bot-data
```

Fix the reported manifest, policy, index, or rules database issue, then export and deploy again.

### GitHub setup pending

Run:

```bash
gh auth status
gh auth refresh -h github.com -s repo -s workflow
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO
```

### Oracle setup pending

Run:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu --bootstrap
```
