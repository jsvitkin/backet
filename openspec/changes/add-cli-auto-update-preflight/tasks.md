## 1. Update Discovery And Cache

- [x] 1.1 Add CLI update data models for installed version, latest version, release URL, wheel URL, update availability, and retry metadata
- [x] 1.2 Add GitHub latest-release discovery using distribution metadata, short timeouts, stable-release semantics, and `packaging.version.Version` comparison
- [x] 1.3 Reuse the configured release artifact pattern to resolve and validate the expected wheel URL for a target version
- [x] 1.4 Add machine-level update cache path support under the existing Backet config directory
- [x] 1.5 Implement update cache read/write behavior with checked timestamp, latest release metadata, and fresh/stale evaluation
- [x] 1.6 Implement human snooze metadata for a declined latest version without suppressing newer future versions
- [x] 1.7 Ensure discovery failures without a cached newer version return a non-blocking "unknown" result for normal command preflight

## 2. Explicit CLI Update Commands

- [x] 2.1 Add a top-level `backet update` command group that skips update preflight
- [x] 2.2 Implement `backet update check` with human output and deterministic `--json` data
- [x] 2.3 Implement `backet update apply` with interactive confirmation when needed and `--yes` for agents
- [x] 2.4 Implement supported updater detection for `pipx`, including a documented override such as `BACKET_PIPX`
- [x] 2.5 Apply CLI package updates by running `pipx install --force <wheel-url>` against the resolved release wheel
- [x] 2.6 Report `cli_update_unsupported` before modification when the current environment cannot run the supported updater
- [x] 2.7 Report "already current" without reinstalling when no newer supported release exists

## 3. Command Preflight Integration

- [x] 3.1 Wire update preflight into normal CLI command execution before command-specific work runs
- [x] 3.2 Skip preflight for `backet --version`, `backet update ...`, and the immediate rerun after a successful update
- [x] 3.3 Classify callers as interactive human or agent/non-interactive using TTY state, `--json`, CI/automation markers, and internal skip state
- [x] 3.4 Prompt interactive users when an update is available, apply accepted updates, and abort the original command if the accepted update fails
- [x] 3.5 Continue the original command and record snooze metadata when an interactive user declines an update
- [x] 3.6 Re-exec the original `backet` command after a successful prompted update with a one-shot skip flag to avoid loops
- [x] 3.7 Emit deterministic `update_required` errors for agent/non-interactive callers before command-specific work runs
- [x] 3.8 Use a stable documented exit code for `update_required` that is distinct from ordinary usage errors
- [x] 3.9 Preserve stdout/JSON contracts so update prompts or notices do not mix prose with machine-readable command output

## 4. Documentation And Agent Contract

- [x] 4.1 Update README install/upgrade docs to describe Backet-managed CLI updates after initial installation
- [x] 4.2 Document the distinction between CLI package updates and `backet skills update`
- [x] 4.3 Document the agent retry contract: on `update_required`, run `backet update apply --yes` and retry the original command
- [x] 4.4 Document machine-level update cache behavior, snoozing, and the supported `pipx` update boundary
- [x] 4.5 Confirm no skill-pack files or per-vault state docs need behavior changes for this slice

## 5. Testing And Release Validation

- [x] 5.1 Add unit tests for version comparison, stable-release discovery, release artifact URL resolution, and prerelease exclusion
- [x] 5.2 Add unit tests for update cache freshness, stale refresh behavior, discovery failure fallback, and declined-version snoozing
- [x] 5.3 Add CLI tests for `backet update check` human and JSON output
- [x] 5.4 Add CLI tests for `backet update apply --yes`, already-current behavior, unsupported updater behavior, and mocked `pipx install --force`
- [x] 5.5 Add preflight tests proving normal commands check before work, update commands skip preflight, and `--version` skips preflight
- [x] 5.6 Add interactive preflight tests for accepted update, failed accepted update, declined update, and original-command rerun behavior
- [x] 5.7 Add agent/non-interactive tests for `update_required` JSON details, stable exit code, and no command-specific work after the signal
- [x] 5.8 Add offline tests proving ordinary commands continue when update discovery fails and no cached update is known
- [x] 5.9 Add regression tests proving CLI update commands do not update skills and do not write `.backet/` vault state
- [x] 5.10 Run the full test suite
- [x] 5.11 Build the wheel and run install or smoke validation that exercises `backet update check` without requiring a live version bump
