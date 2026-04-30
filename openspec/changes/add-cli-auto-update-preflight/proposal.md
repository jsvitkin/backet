## Why

`backet` is distributed as a GitHub release wheel, but installed CLIs do not currently know when a newer release exists or how to move themselves forward. This creates friction for humans and a brittle failure mode for agents, especially when a command would behave better or more safely under a newer CLI version.

## What Changes

- Add a CLI auto-update preflight that runs before normal `backet` commands and checks whether a newer stable CLI release is available.
- For interactive human terminal use, prompt before command execution and, when accepted, apply the update through Backet-managed update plumbing before rerunning the original command.
- For agent and other non-interactive use, avoid prompts and emit a deterministic update-required signal before doing command work, so callers can run Backet's updater and retry the original command.
- Add an explicit CLI update command surface for checking and applying CLI package updates without using external installer snippets.
- Cache update-check results at machine scope so every command performs the preflight without making every invocation depend on a live network request.
- Keep CLI package updates separate from `backet skills update`; skill-pack updates remain independently managed.
- Preserve JSON/stdout contracts by sending human update notices to stderr and returning machine-readable update signals when deterministic output is requested.

Non-goals for this slice:

- Do not silently auto-update without user consent in interactive terminals.
- Do not update the Codex skill pack as part of CLI package updates.
- Do not store update state in `.backet/` vault state or require a vault to check for CLI updates.
- Do not support prerelease, nightly, or branch-based update channels in v1.
- Do not load vault content, rules corpus content, or skill files as part of update checks.

## Capabilities

### New Capabilities

- `cli-auto-update`: Detect, report, and apply available CLI package updates from repository-hosted release artifacts before normal command execution.

### Modified Capabilities

- None.

## Impact

- CLI: adds update preflight behavior to the top-level command lifecycle and a user-facing update command surface.
- Distribution: reuses existing GitHub release metadata, versioned wheel artifact naming, and `pipx`-based install/upgrade path.
- Agent contract: introduces a stable non-interactive update-required signal and retry expectation.
- Machine-level state: stores update-check cache and any snooze metadata outside vault state, alongside existing machine-level Backet metadata.
- Per-vault state: no schema or `.backet/` storage changes; CLI update availability is machine-level state, not campaign canon.
- Skills: no behavior change for skill installation or `backet skills update`; CLI and skill updates continue to ship independently.
- Rules/retrieval: no change to vault indexing, context retrieval, derived memory, or rules ingestion scope.
