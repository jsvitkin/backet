## ADDED Requirements

### Requirement: The setup wizard MUST guide the complete private bot setup flow
The system MUST provide a guided CLI setup flow that walks a user through every supported v1 phase needed to deploy the private Discord bot to an Oracle VM through GitHub Actions.

#### Scenario: Start guided setup
- **WHEN** a user runs `backet bot setup <vault>` for an initialized vault
- **THEN** the system MUST show the setup phases, current completion state, required local prerequisites, and the next recommended action

#### Scenario: Interactive setup performs guided actions
- **WHEN** a user runs `backet bot setup <vault>` in an interactive terminal
- **THEN** the system MUST prompt through the next incomplete phase and perform supported CLI actions such as installing deployment files, collecting non-secret facts, handing secrets to GitHub, validating Discord/SSH, and dispatching deployment when the user confirms
- **AND** the system MUST allow the user to stop after a phase and resume later from saved setup state

#### Scenario: Resume setup
- **WHEN** a user reruns setup after completing one or more phases
- **THEN** the system MUST resume from saved setup state instead of asking again for already validated non-secret facts

#### Scenario: Focus one phase
- **WHEN** a user runs a focused setup command such as `backet bot setup discord <vault>` or `backet bot setup github <vault>`
- **THEN** the system MUST run only that phase and update the shared setup state consistently

#### Scenario: Setup needs external action
- **WHEN** a phase cannot be completed fully by Backet because an external account, browser consent, or missing tool is required
- **THEN** the system MUST report the exact next action, mark the phase pending, and avoid marking the whole setup complete

#### Scenario: Install deployment files
- **WHEN** a user runs `backet bot setup files <vault>` from the private vault repository or passes `--repo-root`
- **THEN** the system MUST create the private deploy workflow and `deploy/bot/*` assets needed by GitHub Actions
- **AND** the system MUST avoid overwriting changed files unless the user explicitly passes the overwrite option
- **AND** the human output MUST summarize created, updated, unchanged, and skipped files without dumping raw structured setup state

### Requirement: Setup state MUST store only committed-safe non-secret facts
The system MUST persist setup progress and non-secret deployment facts in a committed-safe per-vault setup state file while keeping runtime bot configuration separate.

#### Scenario: Write setup state
- **WHEN** a setup phase successfully validates a non-secret fact such as application ID, guild ID, role ID, channel ID, repository name, Oracle host, Oracle user, deploy path, or model metadata
- **THEN** the system MUST write that fact to `.backet/state/bot-setup.yaml`

#### Scenario: Generate runtime config
- **WHEN** setup has enough Discord, access, and answer-mode facts to configure the bot runtime
- **THEN** the system MUST create or update `.backet/state/bot-config.yaml` without copying wizard-only phase diagnostics into runtime config

#### Scenario: Existing runtime config
- **WHEN** a vault already has `.backet/state/bot-config.yaml` but no setup state
- **THEN** the setup wizard MUST import inferable non-secret facts and ask only for missing or unverifiable facts

#### Scenario: Redacted state output
- **WHEN** a user requests setup status as JSON
- **THEN** the system MUST emit deterministic JSON that includes secret names and configured/missing status but never secret values

### Requirement: Setup secrets MUST be handled by secure handoff
The system MUST accept setup secrets only through non-echoing input paths and hand them directly to the configured secret store without persisting the values.

#### Scenario: Store GitHub secret through gh
- **WHEN** `gh` is installed, authenticated, and authorized for the target repository
- **THEN** the wizard MUST set required GitHub Actions secrets using stdin or another non-echoing mechanism that does not place secret values in shell history or process arguments

#### Scenario: GitHub CLI unavailable
- **WHEN** `gh` is missing, unauthenticated, or lacks required scopes
- **THEN** the wizard MUST stop the affected phase, explain how to authenticate or refresh scopes, and report the exact secret names that remain pending

#### Scenario: Verify secret presence
- **WHEN** the wizard checks whether a GitHub secret is configured
- **THEN** it MUST verify by secret name or metadata only and MUST NOT attempt to read the secret value

#### Scenario: Secret appears in error path
- **WHEN** secret handling fails due to validation, subprocess, network, or authentication errors
- **THEN** the system MUST redact captured output and exceptions before displaying or writing diagnostics

### Requirement: Discord setup MUST be guided and API-validated
The system MUST guide Discord application setup from the CLI while using Discord bot APIs to validate and discover configuration after user-approved portal or installation steps.

#### Scenario: Need Discord application
- **WHEN** no Discord application is configured
- **THEN** the wizard MUST open or print the Discord Developer Portal URL and describe the required app, bot, install, and intent settings in terminal output

#### Scenario: Validate bot token
- **WHEN** the user provides a Discord bot token through hidden input or stdin
- **THEN** the wizard MUST validate it with Discord's bot APIs and derive the application ID, application name, bot user ID, and relevant private/public bot warnings where available

#### Scenario: Generate private install URL
- **WHEN** the wizard knows the application ID
- **THEN** it MUST generate an installation URL for Guild Install using the `applications.commands` and `bot` scopes and the configured minimal bot permissions

#### Scenario: Discover guild after install
- **WHEN** the bot has been installed into one or more guilds
- **THEN** the wizard MUST list discoverable guilds and let the user choose the intended private guild by name and ID

#### Scenario: Discover channels and roles
- **WHEN** a target guild is selected and the bot token has sufficient access
- **THEN** the wizard MUST list eligible channels and roles from Discord APIs so the user can map player, Storyteller, and allowed-channel policies without manually copying IDs

#### Scenario: Discord user token offered
- **WHEN** a user attempts to provide a Discord user token, password, cookie, or other user-account credential
- **THEN** the wizard MUST refuse it and explain that Backet only uses bot-token and browser-consent flows

### Requirement: GitHub setup MUST configure deployment inputs from the CLI
The system MUST use GitHub CLI where available to configure repository secrets, repository variables, workflow readiness, and deployment dispatch for the private bot.

#### Scenario: Configure repository secrets
- **WHEN** the wizard has required secret values and an authenticated `gh` session
- **THEN** it MUST configure required repository secrets such as `DISCORD_TOKEN`, `ORACLE_VM_SSH_KEY`, and optional `MODEL_DOWNLOAD_TOKEN`

#### Scenario: Configure repository variables
- **WHEN** the wizard has non-secret deployment facts for GitHub Actions
- **THEN** it MUST configure repository variables such as `DISCORD_GUILD_ID`, `ORACLE_VM_HOST`, `ORACLE_VM_USER`, `BOT_COMPOSE_PROFILES`, and model metadata unless the user chooses to store selected facts as secrets

#### Scenario: Workflow scope missing
- **WHEN** GitHub workflow setup or dispatch fails because the local GitHub token lacks workflow permissions
- **THEN** the wizard MUST explain the missing scope and provide the exact `gh auth refresh` style command needed to continue

#### Scenario: Public repository target
- **WHEN** the target repository is public
- **THEN** the wizard MUST warn that committed vault state and private workflow artifacts may expose campaign or rules-derived data and require explicit confirmation before continuing

### Requirement: Oracle VM setup MUST validate and bootstrap the host over SSH
The system MUST guide setup for an existing SSH-reachable Oracle Always Free VM and validate that the host can run the private bot deployment.

#### Scenario: Validate SSH host
- **WHEN** the user provides an Oracle VM host, username, and SSH credential
- **THEN** the wizard MUST test SSH connectivity and report the detected OS, user, and deploy path without storing the SSH private key value

#### Scenario: Bootstrap supported host
- **WHEN** the target host lacks required directories or container runtime components and the OS is supported
- **THEN** the wizard MAY offer to bootstrap the host remotely after confirmation and MUST report each completed remote setup action

#### Scenario: Unsupported host
- **WHEN** the target host OS, permissions, or package manager cannot be safely bootstrapped by Backet
- **THEN** the wizard MUST fail the Oracle phase with an actionable diagnostic and leave setup pending

#### Scenario: Validate deploy layout
- **WHEN** Oracle setup completes
- **THEN** the wizard MUST verify the expected deploy, upload, release, data, and model-cache paths needed by the private deployment workflow

### Requirement: Vault visibility review MUST gate deployment
The setup wizard MUST review bot visibility policy and block deployment when player-facing access would be unsafe or invalid.

#### Scenario: Visibility policy valid
- **WHEN** the vault has valid bot visibility metadata
- **THEN** the wizard MUST summarize player-visible, Storyteller-only, bot-excluded, unmarked, missing-topic, and invalid-topic counts before deployment

#### Scenario: Visibility policy invalid
- **WHEN** visibility validation reports invalid metadata or ambiguous player-facing policy
- **THEN** the wizard MUST block deployment and offer the guided visibility editor needed to inspect or fix the vault

#### Scenario: No player-visible canon
- **WHEN** no notes are player-visible but setup otherwise succeeds
- **THEN** the wizard MUST warn that player canon answers will be empty or limited and require explicit confirmation before deployment

### Requirement: Deployment MUST be triggerable and watchable from setup
The setup wizard MUST be able to dispatch the private GitHub Actions deployment workflow and report its result from the terminal.

#### Scenario: Trigger deployment
- **WHEN** setup prerequisites pass and `gh` can dispatch workflows for the repository
- **THEN** the wizard MUST trigger the configured deployment workflow with the selected vault path and setup-derived inputs

#### Scenario: Watch deployment
- **WHEN** a deployment run starts
- **THEN** the wizard MUST show or poll the run status, provide the run URL, and summarize success, failure, cancellation, or timeout

#### Scenario: Branch not pushed
- **WHEN** local setup files, workflow files, deploy scripts, or vault changes needed by the workflow have not been pushed
- **THEN** the wizard MUST refuse deployment or warn that GitHub Actions cannot see the local changes

#### Scenario: Deployment fails
- **WHEN** the GitHub Actions deployment run fails
- **THEN** the wizard MUST surface the failing phase, preserve redaction, and leave setup in a state that can be resumed after fixes

### Requirement: Setup diagnostics MUST be redacted and actionable
The system MUST provide setup diagnostics that are safe to display, commit, paste into issues, or inspect through agent workflows.

#### Scenario: Human status output
- **WHEN** a user runs `backet bot setup status <vault>`
- **THEN** the system MUST report phase status, missing prerequisites, configured secret names, configured variable names, warnings, and next actions without displaying secret values

#### Scenario: JSON status output
- **WHEN** a user runs setup status with JSON output
- **THEN** the system MUST emit stable structured data suitable for tests and agents, with all sensitive fields redacted or omitted

#### Scenario: Reset setup state
- **WHEN** a user resets setup state
- **THEN** the system MUST explain which committed-safe files will be changed and MUST NOT attempt to delete or read GitHub secret values

#### Scenario: Doctor detects drift
- **WHEN** setup state, runtime bot config, GitHub variables, or Oracle deploy layout disagree
- **THEN** the setup doctor MUST identify the drift and recommend the smallest setup phase to rerun

### Requirement: Bot command UX MUST be guided in human terminals
The system MUST provide guided human-mode entry points for the private bot command surface while preserving deterministic JSON and focused automation commands.

#### Scenario: Open bot command center
- **WHEN** a user runs `backet bot` in an interactive terminal
- **THEN** the system MUST offer a guided command center for setup, visibility, policy inspection, bundle export, bundle checks, dry-run questions, model checks, and foreground bot runtime

#### Scenario: Open visibility editor
- **WHEN** a user runs `backet bot visibility` in an interactive terminal
- **THEN** the system MUST audit current visibility, explain that unmarked notes remain Storyteller-only, and offer numbered guided actions to mark player-visible, Storyteller-only, excluded, list unclassified notes, or clear metadata

#### Scenario: Choose visibility targets from scanned vault context
- **WHEN** a user marks or clears bot visibility through the guided editor
- **THEN** the system MUST suggest candidate notes and folders from the scanned vault context and also allow a vault-relative path to be typed manually

#### Scenario: Guided visibility write
- **WHEN** a user runs a human-mode visibility write such as `backet bot visibility set`
- **THEN** the system MUST preview the affected notes before writing and ask for confirmation unless the user explicitly bypasses guidance

#### Scenario: Human bot command output
- **WHEN** a user runs bot policy, export, doctor, inspect, ask, model-check, or visibility commands without `--json`
- **THEN** the system MUST show concise summaries and guided next actions instead of raw nested structured dumps or default command recipes
