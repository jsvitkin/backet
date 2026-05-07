## 1. Setup State and Wizard Core

- [x] 1.1 Define `bot-setup.yaml` schema, validation rules, redaction rules, and migration/import behavior from existing `bot-config.yaml`.
- [x] 1.2 Add setup state read/write helpers under the bot setup layer without changing bot runtime config loading.
- [x] 1.3 Implement a reusable setup phase engine with phase status, next actions, pending states, timestamps, and resumable execution.
- [x] 1.4 Add human and JSON output models for setup status, phase results, warnings, and redacted diagnostics.
- [x] 1.5 Add CLI entry points for `backet bot setup`, `status`, `resume`, focused phase commands, `doctor`, `deploy`, and `reset`.

## 2. Secret Handling

- [x] 2.1 Implement hidden-input and stdin secret capture helpers that never echo values or place them in command arguments.
- [x] 2.2 Implement centralized secret redaction for logs, exceptions, subprocess output, JSON, and terminal diagnostics.
- [x] 2.3 Add GitHub secret-name verification that checks configured/missing state without reading secret values.
- [x] 2.4 Add tests proving secret values do not appear in captured CLI output, JSON output, exception messages, or setup state files.

## 3. Discord Setup Phase

- [x] 3.1 Add a Discord setup client for token validation and current application/bot identity discovery.
- [x] 3.2 Add terminal guidance for Developer Portal actions that cannot be automated safely.
- [x] 3.3 Generate the private Guild Install URL with `applications.commands` and `bot` scopes plus minimal configured permissions.
- [x] 3.4 Add post-install discovery for guilds, channels, and roles using bot-token API calls.
- [x] 3.5 Add interactive and JSON-compatible role/channel selection flows that persist selected IDs to setup state.
- [x] 3.6 Add validation and refusal paths for Discord user tokens, missing bot membership, missing guild access, and insufficient API permissions.
- [x] 3.7 Add mocked Discord API tests for token validation, app discovery, guild selection, channel/role selection, and error handling.

## 4. Visibility Review Phase

- [x] 4.1 Reuse existing bot visibility audit and policy validation from the setup wizard.
- [x] 4.2 Add setup output summarizing player-visible, Storyteller-only, bot-excluded, unmarked, invalid-topic, and missing-topic counts.
- [x] 4.3 Block deployment when visibility policy validation is unsafe or invalid.
- [x] 4.4 Add confirmation behavior for zero player-visible notes and tests for both blocking and confirmed-warning paths.

## 5. GitHub Setup Phase

- [x] 5.1 Add a GitHub CLI adapter for `gh auth status`, repository inspection, secret setting, variable setting, workflow listing, workflow dispatch, and run watching.
- [x] 5.2 Classify deploy inputs into default secrets and variables, with an override path for user-selected sensitive variables.
- [x] 5.3 Configure required secrets via `gh secret set` using stdin and required variables via `gh variable set`.
- [x] 5.4 Detect missing `gh`, unauthenticated `gh`, public repository risk, missing workflow file, missing workflow scope, and unpushed local changes.
- [x] 5.5 Add tests with a fake `gh` executable or adapter mock covering success, missing auth, missing workflow scope, public repo confirmation, and failed dispatch.

## 6. Oracle VM Setup Phase

- [x] 6.1 Add SSH target validation that checks host, user, authentication, remote OS, and deploy path without storing private key values.
- [x] 6.2 Add remote deploy doctor checks for Docker, Docker Compose, deploy directories, upload directories, release directories, current data symlink, activation scripts, and model cache path.
- [x] 6.3 Add optional remote bootstrap for supported OS targets after explicit confirmation, including directory creation and container runtime setup where safe.
- [x] 6.4 Add failure paths for unsupported OS, missing sudo, unreachable host, invalid key, and partially configured remote layout.
- [x] 6.5 Add SSH/remote-command tests using adapter mocks for doctor success, bootstrap success, unsupported host, and redacted failures.

## 7. Runtime Config and Deployment Handoff

- [x] 7.1 Generate or update `.backet/state/bot-config.yaml` from validated setup state while preserving unrelated existing config where safe.
- [x] 7.2 Add drift detection between setup state, runtime config, GitHub variables, and Oracle deploy layout.
- [x] 7.3 Wire `backet bot setup deploy` to dispatch the private GitHub Actions deployment workflow with the selected vault path.
- [x] 7.4 Add workflow run watching and terminal summaries for success, failure, cancellation, timeout, and run URL reporting.
- [x] 7.5 Ensure deployment refuses to proceed when required local setup files are not committed and pushed.

## 8. Documentation and Wiki

- [x] 8.1 Rewrite `docs/private-discord-bot.md` so the guided setup flow is the primary path and raw commands are reference material.
- [x] 8.2 Update `docs/wiki/Hosting-Backet-Bot.md` with a user-friendly step-by-step wizard guide.
- [x] 8.3 Document what the GitHub repository must contain for the workflow to work, including `.backet/state/bot-setup.yaml`, `.backet/state/bot-config.yaml`, rules SQLite state when enabled, deploy assets, workflow file, and visibility metadata.
- [x] 8.4 Document exactly which values are GitHub secrets, which are GitHub variables, and how `gh` is used to configure them.
- [x] 8.5 Document Discord setup limits clearly: Backet guides app creation and install consent but does not automate user accounts or ask for user tokens.

## 9. Tests and Validation

- [x] 9.1 Add unit tests for setup state schema validation, import from existing runtime config, redacted JSON, and state reset.
- [x] 9.2 Add CLI golden-output tests for main wizard, focused phases, pending action output, and status/doctor output.
- [x] 9.3 Add integration-style tests with mocked Discord, GitHub CLI, and SSH adapters covering the happy path from setup start to deploy dispatch.
- [x] 9.4 Add regression tests ensuring bot export and runtime loading still use `bot-config.yaml` and do not depend on wizard-only state.
- [x] 9.5 Run the full test suite and `openspec validate add-guided-bot-setup-wizard` before marking implementation complete.

## 10. Release Readiness

- [x] 10.1 Verify generated docs/wiki instructions match the implemented CLI names and prompts.
- [x] 10.2 Verify setup diagnostics remain useful when run in a clean vault, an existing bot-config vault, and a partially configured vault.
- [x] 10.3 Verify a dry-run or mocked end-to-end setup transcript can be included in docs without exposing real IDs or secrets.
- [x] 10.4 Verify the manual GitHub Actions workflow remains usable for users who do not run the wizard deploy phase.

## 11. Human Setup Regression Fixes

- [x] 11.1 Replace generic `CommandResult` printing for `backet bot setup` with a guided human renderer while preserving deterministic `--json`.
- [x] 11.2 Add `backet bot setup files` to install the private deploy workflow and `deploy/bot/*` from the CLI.
- [x] 11.3 Update the private deploy workflow template so vault-only private repositories install the released Backet wheel instead of requiring the Backet source tree.

## 12. Interactive Wizard Regression Fixes

- [x] 12.1 Add a real interactive `backet bot setup` wizard path instead of only a prettier status/next-action report.
- [x] 12.2 Guide and execute the local deployment-files phase from the main wizard with confirmation.
- [x] 12.3 Guide Discord bot-token validation, install URL handoff, guild selection, role selection, and channel selection from the main wizard.
- [x] 12.4 Guide answer-mode selection, including optional Llama model metadata and private model token handoff.
- [x] 12.5 Guide GitHub repository, secret, variable, Oracle fact, SSH validation/bootstrap, and deploy dispatch phases from the main wizard.
- [x] 12.6 Preserve non-interactive human status with `--no-guided` and deterministic machine output with `--json`.
- [x] 12.7 Add CLI regression coverage proving the main wizard installs missing deploy files interactively without raw structured dumps.

## 13. Bot Command Guidance Regression Fixes

- [x] 13.1 Add a guided `backet bot` command center covering setup, visibility, policy, export, bundle checks, dry-run ask, model check, and foreground run.
- [x] 13.2 Add a guided `backet bot visibility` editor for auditing, listing unclassified notes, marking player/Storyteller/excluded visibility, clearing metadata, previewing changes, and confirming writes.
- [x] 13.3 Wire the setup wizard's visibility phase to offer the guided visibility editor before accepting an empty player-visible canon index.
- [x] 13.4 Replace generic human output for bot policy, export, doctor, inspect, ask, model-check, and visibility commands with guided summaries and next actions while preserving `--json`.
- [x] 13.5 Make focused visibility writes interactive in human terminals, with dry-run preview and confirmation by default, while preserving `--yes`, `--no-guided`, and non-interactive behavior.
- [x] 13.6 Add CLI regression tests for the bot command center, visibility wizard, guided visibility writes, and human bot policy output.
- [x] 13.7 Replace terse visibility action codes with a numbered guided editor that suggests fake-vault-derived notes/folders and add an end-to-end wizard test that writes player/excluded metadata without command-recipe output.
