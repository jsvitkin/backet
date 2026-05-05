## Context

The private Discord bot change created a safe hosted runtime: it exports access-scoped vault indexes, uses one shared rules SQLite corpus, runs privately on an Oracle VM, and can optionally use local Llama synthesis. The remaining problem is not bot behavior. It is setup ergonomics.

The current docs ask the user to move between local commands, Discord Developer Portal pages, GitHub repository settings, GitHub Actions, SSH, and VM filesystem layout. That is too much exposed wiring for a deployment flow that handles private canon, copyrighted rules data, SSH credentials, and bot tokens.

The new setup flow should feel like this:

```text
backet bot setup

  local prereqs
       |
       v
  Discord app + invite
       |
       v
  visibility audit
       |
       v
  GitHub secrets + variables
       |
       v
  Oracle VM bootstrap + doctor
       |
       v
  deploy workflow + smoke check
       |
       v
  running private bot
```

External constraints checked during design:

- Discord's current bot quickstart says Guild Install uses the `applications.commands` and `bot` scopes, and the installation prompt is completed in a browser.
- Discord application commands are the primary invocation surface and guild commands can be created with bot-token authorization.
- Discord interactions may arrive over the Gateway, which keeps the current no-public-webhook design valid.
- Discord application and guild APIs expose enough bot-token information to validate the app and discover channels/roles after installation.
- GitHub CLI supports repository secrets and variables, so Backet can set them from the terminal when `gh` is installed and authenticated.

References:

- https://docs.discord.com/developers/quick-start/getting-started
- https://docs.discord.com/developers/interactions/application-commands
- https://docs.discord.com/developers/platform/interactions
- https://docs.discord.com/developers/resources/application
- https://docs.discord.com/developers/resources/guild
- https://cli.github.com/manual/gh_secret_set
- https://cli.github.com/manual/gh_variable_set

## Goals / Non-Goals

**Goals:**

- Provide a guided terminal setup flow that can take a user from "I have a local Backet vault and an Oracle VM" to "the private bot is deployed and smoke-checked."
- Persist all non-secret facts needed to resume setup and redeploy later.
- Keep all secret values out of committed files, logs, manifests, command history, and shell process arguments.
- Use `gh` to set GitHub Actions secrets/variables and trigger deployment when available.
- Use Discord APIs to validate tokens and discover IDs instead of asking the user to copy every snowflake manually.
- Use SSH to validate and bootstrap the Oracle VM instead of telling the user to run a long list of remote commands by hand.
- Keep deployment private: the repository, workflow artifacts, bot bundle, rules SQLite database, vault notes, SSH keys, bot token, and model files stay private.
- Make every setup phase inspectable through human output and redacted JSON.

**Non-Goals:**

- Provision an Oracle Cloud account or create a VM through the OCI API in this change. V1 assumes an SSH-reachable Oracle Always Free VM already exists.
- Fully create or configure the Discord application without the Developer Portal. The wizard can open the portal and validate results, but it must not automate a Discord user account.
- Ask for or use Discord user tokens, passwords, cookies, or browser automation.
- Replace GitHub Actions with direct local SSH deployment.
- Build a GUI.
- Change retrieval permissions, rules corpus structure, Llama prompt boundaries, or runtime answer safety.

## Decisions

### 1. Setup is a resumable CLI phase machine

The primary command is `backet bot setup <vault>`. Focused subcommands are thin entry points into the same setup engine:

```text
backet bot setup status <vault>
backet bot setup resume <vault>
backet bot setup discord <vault>
backet bot setup visibility <vault>
backet bot setup github <vault>
backet bot setup oracle <vault>
backet bot setup deploy <vault>
backet bot setup doctor <vault>
backet bot setup reset <vault>
```

The wizard stores phase status, warnings, timestamps, and next actions. A user can stop after Discord setup, return tomorrow, and continue from GitHub setup without remembering which IDs were already validated.

Alternative considered: add a longer wiki page with clearer commands. Rejected because the user's pain is process coordination, not missing command examples.

### 2. Non-secret setup state is committed under `.backet/state/bot-setup.yaml`

The setup state is a commit-safe, portable file. It is allowed to contain facts that are already visible to a server admin, repository collaborator, or Discord API caller:

```yaml
schema_version: 1
setup:
  completed_phases:
    - prerequisites
    - discord
  last_checked_at: "2026-05-05T12:00:00Z"
discord:
  app_id: "123456789012345678"
  app_name: "Backet Bot"
  bot_user_id: "234567890123456789"
  guild_id: "345678901234567890"
  guild_name: "Prague by Night"
  invite_url: "https://discord.com/oauth2/authorize?client_id=..."
  selected_channel_ids:
    canon: ["456789012345678901"]
  selected_role_ids:
    player: ["567890123456789012"]
    storyteller: ["678901234567890123"]
github:
  repository: "owner/private-vault"
  workflow_file: "deploy-backet-bot.yml"
  variable_names:
    - DISCORD_GUILD_ID
    - ORACLE_VM_HOST
  secret_names:
    - DISCORD_TOKEN
    - ORACLE_VM_SSH_KEY
oracle:
  host: "203.0.113.10"
  user: "ubuntu"
  deploy_path: "/srv/backet-bot"
answers:
  mode: "template"
  llama_profile: null
```

The bot runtime config remains `.backet/state/bot-config.yaml`. The wizard can create or update that file, but runtime code does not read wizard-only progress state.

Alternative considered: store everything in `bot-config.yaml`. Rejected because runtime config and setup progress have different lifecycles. Runtime config should stay small and declarative; setup state needs diagnostics, phase status, and GitHub/Oracle bookkeeping.

### 3. Secrets are handed directly to GitHub, never stored by Backet

The wizard supports hidden prompts and stdin for secret input. When `gh` is present and authenticated, Backet sends secret bytes to `gh secret set` through stdin or an equivalent non-echoing subprocess pipe. Secret values must not appear in command-line arguments, process titles, logs, JSON output, tracebacks, config files, or shell history.

Default classification:

```text
GitHub secrets:
  DISCORD_TOKEN
  ORACLE_VM_SSH_KEY
  MODEL_DOWNLOAD_TOKEN       optional

GitHub variables:
  DISCORD_GUILD_ID
  ORACLE_VM_HOST
  ORACLE_VM_USER
  BOT_COMPOSE_PROFILES
  LLAMA_MODEL_RELATIVE_PATH
  LLAMA_MODEL_SHA256
  LLAMA_MODEL_URL            unless the URL itself contains credentials
```

If a user wants to hide host/user/model URL as well, the wizard may offer a "store deploy facts as secrets" mode, but v1 defaults to variables for non-secret facts.

`gh` is preferred, not mandatory. If it is missing, unauthenticated, or lacks required scopes, the wizard stops the phase and prints exact next commands such as `gh auth login`, `gh auth refresh -h github.com -s repo -s workflow`, or `gh secret set DISCORD_TOKEN --repo owner/repo`. It records the phase as pending instead of pretending setup succeeded.

Alternative considered: ask the user to set all secrets manually in GitHub's web UI. Rejected as the default because the user explicitly wants a CLI-guided flow, and `gh` can safely do this.

### 4. Discord setup is guided, validated, and API-assisted

Backet cannot safely create the Discord application from scratch because that would require user-account automation. The wizard therefore does the next best thing:

1. Opens or prints the Discord Developer Portal URL.
2. Tells the user exactly what to create or toggle:
   - create application
   - add bot user
   - reset/copy bot token
   - keep Message Content Intent disabled
   - turn off public bot installation where Discord exposes that setting
   - use Guild Install with `applications.commands` and `bot`
3. Accepts the bot token through a hidden prompt.
4. Validates the token with Discord's bot APIs.
5. Discovers application ID and bot user ID from the current application/user response.
6. Generates a private install URL.
7. Opens or prints the install URL so the user authorizes the app into the private server.
8. Lists guilds visible to the bot, then channels and roles in the selected guild.
9. Lets the user pick channel and role mappings by name in the terminal.

After the bot is installed, Backet should not ask the user to enable Discord Developer Mode just to copy IDs. It can discover roles and channels through bot-token API calls, then persist the selected IDs.

Alternative considered: ask the user to copy all IDs manually from Discord. Rejected as the primary path because it is error-prone and exactly the sort of work the wizard can remove.

### 5. GitHub Actions remains the deployment authority

V1 deployment flow:

```text
local Backet wizard
  |
  | gh secret set / gh variable set
  | gh workflow run
  v
private GitHub Actions runner
  |
  | export bot bundle
  | upload private artifact to VM
  | activate release
  | restart containers
  | smoke check
  v
Oracle VM
```

The wizard must verify:

- `gh auth status` succeeds for the target host.
- The target repository is private or the user explicitly accepts the risk.
- The current branch and setup files are pushed before triggering deployment.
- The workflow file exists in `.github/workflows/`.
- The local GitHub token has `workflow` scope when workflow files need to be pushed or workflow dispatch fails.
- Required secrets and variables exist by name.

The wizard can run `gh workflow run` and then `gh run watch` or equivalent polling. It should summarize run status and show the GitHub run URL.

Alternative considered: direct deploy from the local machine over SSH. Rejected for v1 because the user already accepts GitHub Actions, and using Actions keeps deployment reproducible from committed vault state.

### 6. Oracle VM setup is remote-bootstrap, not cloud-provisioning

The setup wizard assumes the Oracle VM already exists and is reachable over SSH. It handles the host-level work:

- SSH connectivity check.
- OS detection.
- Optional remote Docker/Compose bootstrap for recognized supported systems when the user confirms sudo use.
- `/srv/backet-bot` layout creation.
- deploy script upload or verification.
- model cache directory verification.
- smoke command execution.

If the OS is unsupported or sudo is unavailable, the wizard fails with a precise diagnostic and leaves the phase pending. It should not paste a dozen remote commands as if setup had succeeded.

Alternative considered: use OCI CLI to create the Always Free VM. Rejected for this change because Oracle account creation, tenancy policy, compartment selection, image selection, network security lists, and quota handling are a separate cloud-provisioning product surface. We can add that later if the Oracle setup itself becomes the bottleneck.

### 7. The wizard includes vault visibility review as a first-class phase

The wizard does not replace `backet bot visibility ...`; it orchestrates it. Before deployment, it must summarize:

- player-visible notes
- Storyteller-only notes
- bot-excluded notes
- unmarked notes
- missing/invalid topics
- rules corpus presence
- what a player can query

If policy validation fails, setup continues only after the user fixes visibility metadata. This keeps the deployment flow from shipping a bot that is technically online but unsafe or useless.

### 8. Human output and JSON output are both supported

Human output should be conversational and guided:

```text
Discord setup

Found bot: Backet Bot (234567890123456789)
Found server: Prague by Night (345678901234567890)

Choose the player role:
  1. Players
  2. Guests
  3. Storyteller
```

JSON output is deterministic and redacted:

```json
{
  "phase": "discord",
  "status": "needs_action",
  "safe_state_path": ".backet/state/bot-setup.yaml",
  "secrets": {
    "DISCORD_TOKEN": "configured"
  },
  "next_actions": [
    "Install the app into the selected guild, then rerun setup discord."
  ]
}
```

Alternative considered: interactive-only setup. Rejected because agents, tests, and CI need deterministic outputs.

## Risks / Trade-offs

- Secret leakage through logs or process args -> Use hidden input, subprocess stdin, redaction helpers, tests against captured output, and a rule that secret values never appear in exception messages.
- Discord API or installation UX changes -> Keep Discord calls in one client module, cite official docs in developer docs, and make setup diagnostics explain which call failed.
- GitHub token lacks workflow scope -> Detect before deploy, recommend `gh auth refresh`, and explain that workflow-file pushes require extra scope.
- Oracle VM OS variance -> Support a small matrix first, make remote doctor explicit, and fail pending rather than half-configuring an unknown host.
- User's repository is public -> Warn loudly before configuring deployment; require explicit confirmation because workflow artifacts and committed `.backet` state may reveal private campaign structure even without secrets.
- Local Llama is slow on Always Free resources -> Keep template answer mode as the default and require Llama fallback to template when enabled.
- Setup state drifts from runtime config -> Generate runtime config from setup state, include fingerprints/timestamps, and make `backet bot setup doctor` report drift before deployment.

## Migration Plan

1. Existing users with `.backet/state/bot-config.yaml` can run `backet bot setup import` or the main wizard; Backet reads the runtime config and creates `.backet/state/bot-setup.yaml` with any non-secret facts it can infer.
2. Existing GitHub secrets remain valid. The wizard verifies names and marks them configured without reading values.
3. Existing Oracle VM layouts remain valid if `backet bot setup oracle` passes doctor checks.
4. Existing manual deploy workflow remains runnable from GitHub Actions. The wizard adds a terminal-first path on top of it.
5. Rollback stays the existing release-directory rollback on the VM; this change does not alter release activation semantics.

## Open Questions

There are no blocking architecture questions for v1. Remaining choices are implementation-level naming and UX copy details, such as the exact prompt text for role/channel selection.
