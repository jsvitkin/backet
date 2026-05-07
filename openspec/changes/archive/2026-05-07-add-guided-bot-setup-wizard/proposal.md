## Why

The private Discord bot can be hosted, but the current setup path still expects the Storyteller to translate documentation into a sequence of local, Discord, GitHub, and VM steps. That is brittle for a secrets-heavy deployment flow: the product should guide the user through the whole path from local vault to a running private bot without leaving hidden prerequisites in prose.

## What Changes

- Add a guided CLI setup wizard for the private Discord bot, centered on `backet bot setup`, that walks through prerequisites, Discord application setup, vault visibility review, GitHub repository configuration, Oracle VM validation, deployment, and smoke checks.
- Add resumable setup state under `.backet/state/bot-setup.yaml` for non-secret facts such as application ID, bot user ID, guild ID, selected channel IDs, selected role IDs, repository name, Oracle VM host/user, deploy path, answer mode, and model metadata.
- Keep runtime bot configuration in `.backet/state/bot-config.yaml`; the wizard may create or update it from setup state, but bot runtime behavior continues to read the runtime config rather than wizard-only state.
- Add secure secret handling to the wizard: Discord bot token, Oracle SSH private key, and optional model download token are accepted through hidden prompts or stdin, sent directly to GitHub with `gh secret set` when available, and never written to vault state, logs, config files, bundle manifests, or docs.
- Add GitHub CLI integration so Backet can set repository secrets and variables, verify their presence, trigger the manual deployment workflow, and watch or summarize the run from the terminal.
- Add Discord setup guidance that is CLI-first but honest about Discord's boundaries: Backet can open the Developer Portal and installation URL, then validate the resulting bot token and discover application, guild, role, and channel IDs through Discord APIs after the bot has been added to the server.
- Add Oracle Always Free VM setup guidance and checks: validate SSH connectivity, remote deploy directory layout, Docker/Compose availability, release directories, model cache path, and the remote activation scripts required by the existing private deploy workflow.
- Add a user-friendly terminal flow with status, resume, skip, dry-run, explain, redacted JSON, and clear next-action output for every phase.
- Add setup-aware documentation that describes the guided command flow first and treats raw commands as reference material, not the primary setup experience.

### Non-Goals

- Do not implement a GUI or web dashboard for setup in this slice.
- Do not fully automate Discord application creation, bot token reset, or server authorization through user-account automation. Backet must not request Discord passwords, browser cookies, or user tokens.
- Do not replace GitHub Actions with direct local SSH deployment in v1. The supported v1 deploy path is "local wizard configures and triggers private GitHub Actions."
- Do not publish a public bot, public bundle, public image containing private data, or public install flow.
- Do not store secrets in the vault, repository, setup state, runtime config, bundle, Docker Compose file, or OpenSpec/docs.
- Do not change the bot's retrieval or permission safety model: authorization still happens before retrieval, and hidden material is still never retrieved for lower tiers.
- Do not add multi-cloud hosting automation. Oracle Always Free VM remains the first guided target.

## Capabilities

### New Capabilities

- `bot-setup-wizard`: Guided CLI setup, resumable setup state, Discord/GitHub/Oracle discovery and validation, secure secret handoff, deployment triggering, smoke checks, and user-friendly setup documentation.

### Modified Capabilities

- `bot-deployment-bundles`: Deployment automation must be invocable from the setup wizard through GitHub Actions, and deployment docs/prerequisite checks must account for wizard-managed non-secret setup state and GitHub secrets/variables.

## Impact

- CLI: adds `backet bot setup` plus focused subcommands such as `status`, `resume`, `discord`, `visibility`, `github`, `oracle`, `deploy`, `doctor`, and `reset` where those make the flow clearer.
- Per-vault state: adds committed, portable `.backet/state/bot-setup.yaml` for non-secret setup facts; keeps `.backet/state/bot-config.yaml` as the bot runtime config; keeps machine-specific scratch and credentials ignored.
- GitHub integration: requires optional `gh` CLI support for secrets, variables, workflow dispatch, workflow run inspection, and authentication diagnostics. If `gh` is missing or unauthorized, the wizard must provide exact fallback steps and mark the phase pending.
- Discord integration: uses official Discord bot/application APIs for validation and discovery after the user creates the app and installs it into the guild. The wizard must never depend on Message Content Intent or user-account automation.
- Oracle VM integration: validates an SSH-accessible host with Docker/Compose and the expected `/srv/backet-bot` style layout before deployment.
- Docs/wiki: guided setup becomes the primary how-to; command catalogs remain as reference.
- Tests: add unit tests for setup state redaction and validation, mocked Discord/GitHub/SSH integration tests, CLI golden-output tests for wizard phases, and smoke tests for workflow/deploy handoff.
