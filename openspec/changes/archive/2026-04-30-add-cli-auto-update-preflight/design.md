## Context

`backet` is currently installed as a machine-level CLI from versioned GitHub release wheels, normally through `pipx`. The installed CLI exposes `--version`, vault operations such as `init`, `doctor`, `index`, `context`, and independent skill-pack operations such as `backet skills install` and `backet skills update`.

The current release path already has most of the raw material needed for CLI updates:

```text
repository/
  metadata/compatibility.json   # repository, default ref, wheel artifact pattern
  scripts/install.sh            # pipx install from latest or requested release
  scripts/upgrade.sh            # wrapper around install.sh
  src/backet/distribution.py     # release artifact URL helpers
  src/backet/cli.py              # Typer command surface and global --json/--version handling

machine/
  pipx-managed backet CLI        # current executable package
  Backet config dir              # machine-level metadata, not vault state

target vault/
  .backet/                       # per-vault state and derived memory
  campaign notes                 # human-authored canon
```

The missing layer is an update-aware command lifecycle. Users should not need to remember an external installer command once `backet` is installed, and agents should not proceed with stale CLI behavior when Backet can tell them a newer version is available.

This change affects CLI/distribution behavior only. It must not change retrieval scope, vault indexing, memory rebuilding, rules ingestion, or skill-pack update semantics.

## Goals / Non-Goals

**Goals:**

- Run an update preflight before normal `backet` command work.
- Prompt interactive users when a newer stable CLI release is available, apply the update on acceptance, and rerun the original command under the updated CLI.
- Give agents and other non-interactive callers a deterministic update-required signal instead of an interactive prompt.
- Provide explicit `backet update` commands for checking and applying CLI package updates.
- Cache update discovery at machine scope so the preflight happens every time without forcing a live GitHub request every time.
- Keep stdout and JSON contracts deterministic for agent-facing calls.
- Keep CLI package updates separate from skill-pack updates and per-vault state.

**Non-Goals:**

- No silent interactive auto-update without consent.
- No automatic skill-pack update as part of CLI package update.
- No prerelease, branch, nightly, or channel selection in v1.
- No public package index dependency.
- No vault schema migration or `.backet/` state change.
- No retrieval, indexing, memory, or rules behavior change.

## Decisions

### 1. Add an update preflight to normal command execution

The top-level CLI callback should initialize normal command state and then run an update preflight for ordinary commands before any command-specific work happens.

```text
backet <command>
  |
  v
update preflight
  |
  +-- no update known -> run original command
  |
  +-- interactive update available -> prompt, update, re-exec original command
  |
  +-- non-interactive update available -> emit update_required and exit
```

The preflight must be skipped for commands that are themselves part of update handling, for `--version`, and for internal reruns after a successful update. The rerun should use an internal environment flag such as `BACKET_SKIP_UPDATE_CHECK=1` to avoid loops.

Alternative considered:

- Only add `backet update check`. Rejected because it relies on humans and agents remembering to ask before doing real work, which is exactly the failure mode this feature is meant to remove.

### 2. Treat every invocation as a preflight, but cache network discovery

Every normal command should pass through the preflight. The preflight should use a machine-level cache before deciding whether to contact GitHub.

Recommended v1 cache behavior:

- Store update metadata under the existing machine config directory, for example `update-check.json`.
- Cache latest stable version, release URL, wheel URL, checked timestamp, and any human snooze for a declined version.
- Treat cache entries as fresh for 24 hours by default.
- Use a short network timeout when refreshing stale cache.
- If the network is unavailable and no cached update is known, continue the requested command.
- If the cache already knows a newer version is available, act on that result even if the current network check fails.

Alternative considered:

- Hit GitHub on every command. Rejected because normal CLI latency and reliability should not depend on a live network request for each invocation.

### 3. Discover only stable repository releases in v1

Version discovery should use the configured repository from distribution metadata and GitHub's latest stable release behavior. Tags should be normalized by removing a leading `v` and compared with `packaging.version.Version`.

The resolved wheel URL should continue to come from the existing release artifact pattern:

```text
https://github.com/{repository}/releases/download/v{version}/backet-{version}-py3-none-any.whl
```

The update engine should validate that the target version is newer than the installed version and that the artifact name matches the configured wheel pattern before applying an update.

Alternative considered:

- Track `main` or prereleases. Rejected for v1 because pre-command update prompts should be boring and stable, not a channel-management system.

### 4. Use Backet-managed pipx update plumbing, not remote shell snippets

Interactive users should never be told to paste a curl command as the primary update path. Once Backet is installed, Backet should perform its own CLI package update.

The updater should install the resolved wheel using the same supported package manager boundary as the installer:

```text
pipx install --force <wheel-url>
```

The updater may locate `pipx` from PATH or a documented override such as `BACKET_PIPX`. If the current installation is not updateable by the supported mechanism, the updater should fail before modifying anything with a clear `cli_update_unsupported` error.

After a successful update, the old process must not continue into command work. It should replace itself with a new `backet <original args>` process and set the internal skip flag.

Alternative considered:

- Execute `scripts/upgrade.sh` through a downloaded shell command. Rejected because self-update should not depend on executing remote shell text at runtime.

### 5. Use different behavior for humans and agents

The preflight should classify the caller before deciding how to respond to an available update.

Recommended v1 classification:

- Interactive human: stdin and stderr are TTYs, `--json` is not active, and CI mode is not detected.
- Agent/non-interactive: `--json` is active, stdin/stderr is not interactive, or an explicit agent/automation environment marker is present.
- Update commands: always skip preflight and run their requested update behavior directly.

Interactive flow:

```text
A newer Backet is available: 0.1.2 -> 0.1.3
Update now? [Y/n]
```

- Yes: apply update, re-exec the original command.
- No: record a short snooze for that latest version and continue the original command.

Agent/non-interactive flow:

```text
code: update_required
installed_version: 0.1.2
latest_version: 0.1.3
retry_after_update: true
```

For `--json`, the update-required response should use the existing JSON error envelope with stable details and a documented retry hint. A distinct exit code, such as `75`, should indicate that the command did not run and can be retried after `backet update apply --yes`.

Alternative considered:

- Prompt in all modes. Rejected because prompts in agent and CI contexts are brittle and can hang workflows.

### 6. Preserve command output contracts

Human update notices and prompts should not contaminate JSON success payloads. For normal human output, update notices may be displayed before the command's normal output. For JSON output, an available update should be emitted as a structured error and the requested command should not run.

This matters because agents may parse stdout from `--json` commands such as `backet context`. The update preflight must never produce a mixture of prose and JSON on stdout.

Alternative considered:

- Let the prompt print through the same output path as normal commands. Rejected because it would break deterministic parsing.

### 7. Add explicit CLI update commands

The preflight needs a public update surface that agents can call and humans can use directly:

```text
backet update check
backet update apply
backet update apply --yes
```

`backet update check` should report installed version, latest version, whether an update is available, and release metadata. `--json` should return the same data deterministically.

`backet update apply` should resolve the requested or latest stable version, validate that it is newer unless forced by an explicit version, install the release wheel through the supported mechanism, and report the installed version. `--yes` suppresses confirmation for agents.

Alternative considered:

- Make the preflight the only update path. Rejected because agents need an explicit command to satisfy the retry contract, and humans need a direct way to check or repair update state.

### 8. Keep CLI update state machine-level and separate from skills

Update cache and snooze metadata belong under the machine-level Backet config directory, not in any vault.

```text
machine config/
  skills-installed.json
  update-check.json

vault/
  .backet/
    state/
    memory/
    rules/
```

The skill pack remains separately installable and updateable through `backet skills install` and `backet skills update`. CLI updates may make a previously incompatible skill pack compatible, but the CLI update command must not update skills automatically.

Alternative considered:

- Store update state in `.backet/`. Rejected because one installed CLI can manage multiple vaults, and CLI update availability is not campaign state.

### 9. Prefer fail-safe behavior around update failures

If a user accepts an update and the update fails, Backet should report the failure and not continue into the original command. At that point the user explicitly chose to move to the newer CLI first, and continuing with old behavior can be surprising.

If update discovery fails before any update is known, Backet should continue the original command, except for explicit `backet update check --fresh` or `backet update apply`, where failure is the point of the command.

Alternative considered:

- Always abort when update discovery fails. Rejected because ordinary command use should remain usable offline.

## Risks / Trade-offs

- [Update checks add latency] -> Use cache, short timeouts, and no network request when cache is fresh.
- [Interactive prompts become annoying] -> Record a short snooze when the user declines a specific latest version.
- [Self-update loops after re-exec] -> Set an internal skip flag only for the immediate rerun and skip preflight for update commands.
- [Agents parse mixed output] -> Emit update-required as a structured error for `--json` and avoid prose on stdout.
- [Unsupported installs cannot update themselves] -> Detect unsupported update mechanisms before modification and return `cli_update_unsupported`.
- [A newly installed process still starts old code] -> Re-exec `backet` after update so the original command runs under the new entry point.
- [GitHub is unreachable] -> Continue ordinary commands when no cached update is known, while explicit update commands fail clearly.
- [Repository metadata is wrong] -> Reuse distribution metadata tests and add artifact URL validation around update discovery and apply.

## Migration Plan

1. Add update discovery and version comparison helpers using existing distribution metadata.
2. Add machine-level update cache path support and cache read/write behavior.
3. Add `backet update check` and `backet update apply` command surfaces.
4. Add the preflight hook to normal CLI execution with interactive, non-interactive, and skip-flag behavior.
5. Add output handling for update prompts, JSON update-required responses, and stable exit codes.
6. Update README install/upgrade documentation to describe Backet-managed CLI updates and keep skill updates separate.
7. Add unit, CLI integration, and subprocess-mocked update tests.
8. Validate release artifacts with the new update command in smoke coverage where practical.

Rollback:

- The preflight can be disabled by removing the callback hook while keeping explicit `backet update` commands.
- Machine-level `update-check.json` can be ignored by older releases and safely deleted by users.
- No vault migration rollback is needed because this change does not write vault state.

## Open Questions

- None.
