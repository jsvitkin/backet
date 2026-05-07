# Hosting Backet Bot

This is the friendly path for getting your private Backet Bot into your Discord server.

The main command is:

```bash
backet bot setup /path/to/vault
```

In an interactive terminal this is a guided wizard. It prompts you phase by phase, installs local deploy files when you confirm, asks for secrets through hidden input or file paths, uses `gh` for GitHub setup, validates Discord through the bot API, SSH-checks the Oracle VM, and offers to dispatch the deploy workflow.

You can also start from the bot command center:

```bash
backet bot
```

That menu guides setup, visibility, policy review, export, bundle checks, dry-run questions, model checks, and foreground bot runtime.

For paste-safe status without prompts:

```bash
backet bot setup --no-guided /path/to/vault
```

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

You can stop whenever the wizard asks to continue. Run the same command again later and it resumes from `.backet/state/bot-setup.yaml`.

Backet creates:

```text
.backet/state/bot-setup.yaml
```

This file stores non-secret setup facts, such as app ID, server ID, role IDs, GitHub repo, Oracle host/user, deploy path, and answer mode.

Secrets are never stored there.

If Backet says the deployment workflow or deploy assets are missing, the wizard asks whether to install them. The focused command is also available:

```bash
backet bot setup files /path/to/vault
```

Run this from the private vault repository. If your vault is not the repository root, point Backet at the repo:

```bash
backet bot setup files /path/to/vault --repo-root /path/to/private-repo
```

This creates `.github/workflows/deploy-backet-bot.yml` and `deploy/bot/*`. Review, commit, and push them before deploying.

## 2. Set Up Discord

The main wizard guides this phase. The focused command is:

```bash
backet bot setup discord /path/to/vault
```

Backet tells you to open the Discord Developer Portal and:

- create an application
- add a bot
- keep Message Content Intent off
- use Guild Install
- use the `applications.commands` and `bot` scopes
- install the bot only into your private server

In the interactive wizard, paste the bot token into the hidden prompt. For the focused command, pass it through stdin:

```bash
backet bot setup discord /path/to/vault --token-stdin
```

Paste the token and press Enter.

After the bot is installed in your server, the wizard lists visible servers, roles, and channels so you can choose by number. If you already know the IDs, the focused command accepts them:

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

The setup wizard runs this review before deployment. If player-visible canon is empty, it offers to open the visibility editor. You can open that editor directly:

```bash
backet bot visibility
```

From outside the vault:

```bash
backet bot visibility --vault /path/to/vault
```

It audits the vault, explains that unmarked notes stay Storyteller-only, then shows numbered choices:

- mark player-facing notes as player-visible
- mark hidden notes as Storyteller-only
- exclude notes from bot export
- review unclassified notes
- clear bot visibility metadata
- refresh or finish

When you choose a write action, the editor suggests notes and folders from the scanned vault. Pick a number or type a vault-relative path, review the dry-run preview, then confirm before files are changed.

The focused audit command is:

```bash
backet bot setup visibility /path/to/vault
```

If players should see a folder, choose the player-visible action in the editor, select the suggested folder, keep the default `canon` topic if appropriate, and confirm the preview. For automation or scripts, the focused command remains available:

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

The wizard asks for the Oracle host, SSH user, deploy path, and local key path for validation. The focused command is:

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

The wizard asks for the private repository, sends required secrets to `gh secret set`, and writes non-secret deploy facts to GitHub variables. The focused command is:

```bash
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO
```

Set secrets through focused commands:

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

The workflow installed by `backet bot setup files` installs the released Backet wheel with bot dependencies. Your private vault repository does not need to contain the Backet source tree.

## 6. Commit And Push

Before deploying, commit and push:

- `.backet/state/bot-setup.yaml`
- `.backet/state/bot-config.yaml`
- visibility metadata changes
- rules SQLite state if needed
- deploy assets and workflow files

GitHub Actions can only deploy what exists in the repository.

## 7. Deploy

The wizard offers to deploy after all previous phases pass. The focused command is:

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

## Local Answer Playground

When a Discord answer looks wrong, test the same question locally first:

```bash
backet bot playground /path/to/vault "How does social combat work?" --command rules.ask --role-id player-role --limit 8
```

From inside the vault directory, you can also run:

```bash
backet bot playground "Whats the hunting dicepool for an alley cat predator type vampire" --command rules.ask --role-id player-role
```

You can test several questions in one run:

```bash
backet bot playground /path/to/vault \
  --question "How long does it take to perform rituals in general?" \
  --question "My character rolled a messy critical on their wits + awareness roll. what are the potential messy consequences?" \
  --question "Whats a blood hunt?" \
  --command rules.ask \
  --limit 8
```

The playground exports a temporary bot bundle, answers in fast template mode, and shows which sources were retrieved with scores and match reasons. Use `--use-model` only when you want to test the configured local Llama endpoint. Use `--bundle-output dist/bot-playground --force` if you want to keep the bundle for manual inspection.

Current template answers are tuned to answer directly instead of dumping raw retrieval snippets. Broad rules questions should produce a short procedure-oriented explanation. Specific lookup questions should put the requested value first. Internal source labels such as `[R1]` should not appear in the answer body; source details belong after the answer.

## Answer Logs

When the bot runs in Discord, each command writes a structured diagnostic log. It includes the command route, access tier, number of sources, answer mode, fallback reason, response size, elapsed time, and a question fingerprint.

The logs are paste-safe by default:

- no raw question text
- no vault note paths
- no vault note titles
- no token or key values

For a private debug session only, set `BACKET_BOT_LOG_QUESTION_TEXT=1` in the runtime environment to include a short question preview. Turn it off again after reproducing the issue.

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

- open the visibility editor and mark player-facing notes
- rerun the visibility setup check
- redeploy

Llama is slow:

- use template mode
- use a smaller Q4 GGUF model
- keep template fallback enabled
