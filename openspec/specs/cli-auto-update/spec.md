# cli-auto-update Specification

## Purpose
TBD - created by archiving change add-cli-auto-update-preflight. Update Purpose after archive.
## Requirements
### Requirement: Normal CLI commands MUST run an update preflight before command work

The system MUST check CLI update state before executing normal `backet` commands, while avoiding update recursion and preserving explicit version/update operations.

#### Scenario: Preflight runs before a normal command

- **WHEN** a user or agent invokes a normal `backet` command such as `backet index` or `backet context`
- **THEN** the system MUST evaluate whether a newer supported CLI release is available before the command performs command-specific work

#### Scenario: Update commands skip update preflight

- **WHEN** a user or agent invokes a CLI update command
- **THEN** the system MUST NOT run the update preflight before that update command executes

#### Scenario: Version output skips update preflight

- **WHEN** a user or agent invokes `backet --version`
- **THEN** the system MUST report the installed version without requiring update discovery first

#### Scenario: Rerun after update skips one preflight

- **WHEN** the system successfully applies an update and reruns the original command
- **THEN** the rerun MUST skip the update preflight for that immediate command execution

### Requirement: Update discovery MUST use repository-hosted stable release artifacts

The system MUST discover CLI package updates from the configured repository's stable releases and resolve install targets using the configured release wheel artifact pattern.

#### Scenario: Newer stable release exists

- **WHEN** the configured repository exposes a stable release newer than the installed CLI version
- **THEN** the system MUST identify the newer version and resolve the expected repository-hosted wheel artifact URL

#### Scenario: Latest release is not newer

- **WHEN** the latest stable release is equal to or older than the installed CLI version
- **THEN** the system MUST report that no CLI package update is required

#### Scenario: Prerelease is available

- **WHEN** a prerelease exists that is newer than the installed CLI version
- **THEN** the system MUST NOT require updating to that prerelease in v1

### Requirement: Update discovery MUST NOT use cached release metadata

The system MUST decide CLI update availability from live repository release discovery and MUST NOT use cached latest-version, release URL, wheel URL, or update-availability metadata.

#### Scenario: Normal preflight performs live discovery

- **WHEN** a normal command runs
- **THEN** the system MUST attempt live repository release discovery before deciding whether an update is available

#### Scenario: Explicit check performs live discovery

- **WHEN** a user or agent runs `backet update check`
- **THEN** the system MUST query the configured repository even if older update metadata exists on the machine

#### Scenario: Discovery fails

- **WHEN** update discovery fails during normal command preflight
- **THEN** the system MUST continue the original normal command rather than blocking ordinary offline use
- **AND** the system MUST NOT fall back to cached release metadata

#### Scenario: Snooze state is machine-level

- **WHEN** an interactive user declines an update prompt
- **THEN** the system MAY write machine-level snooze metadata for that latest version
- **AND** the system MUST write it outside the target vault and outside `.backet/` per-vault state

### Requirement: Interactive users MUST be prompted and updated before command execution

The system MUST prompt interactive users when a newer CLI release is available and MUST apply accepted updates before the originally requested command performs work.

#### Scenario: Interactive user accepts update

- **WHEN** an interactive user invokes a normal command and a newer CLI release is available
- **THEN** the system MUST ask whether to update now, apply the update when accepted, and rerun the original command under the updated CLI

#### Scenario: Interactive user declines update

- **WHEN** an interactive user declines an available update prompt
- **THEN** the system MUST continue the original command and record a short machine-level snooze for that latest version

#### Scenario: Accepted update fails

- **WHEN** an interactive user accepts an available update and the update cannot be applied
- **THEN** the system MUST report the update failure and MUST NOT continue into the original command

### Requirement: Non-interactive callers MUST receive a deterministic update-required signal

The system MUST avoid interactive prompts for agents, JSON callers, CI, and other non-interactive contexts when an update is available.

#### Scenario: Agent command sees available update

- **WHEN** an agent or non-interactive caller invokes a normal command and a newer CLI release is available
- **THEN** the system MUST emit an `update_required` signal before command-specific work runs

#### Scenario: JSON caller sees available update

- **WHEN** a caller invokes a normal command with `--json` and a newer CLI release is available
- **THEN** the system MUST emit a deterministic JSON error that includes installed version, latest version, release URL, update command, and retry-after-update metadata

#### Scenario: Agent retries after update

- **WHEN** an agent receives an `update_required` signal
- **THEN** the system MUST provide enough structured guidance for the agent to run `backet update apply --yes` and then retry the original command

#### Scenario: Non-interactive update signal exits distinctly

- **WHEN** the system emits an `update_required` signal for a non-interactive caller
- **THEN** the command MUST exit with a stable documented exit code distinct from ordinary usage errors

### Requirement: The CLI MUST provide explicit update commands

The system MUST expose Backet-managed commands for checking and applying CLI package updates without requiring users to run external installer snippets.

#### Scenario: Check update status

- **WHEN** a user or agent runs `backet update check`
- **THEN** the system MUST report installed version, latest stable version, update availability, and release metadata

#### Scenario: Apply latest update

- **WHEN** a user or agent runs `backet update apply`
- **THEN** the system MUST install the latest supported CLI release when it is newer than the installed version

#### Scenario: Apply update non-interactively

- **WHEN** an agent runs `backet update apply --yes`
- **THEN** the system MUST attempt the update without requiring an interactive confirmation prompt

#### Scenario: No update is available

- **WHEN** a user or agent runs `backet update apply` and no newer supported CLI release exists
- **THEN** the system MUST report that the installed CLI is already current without reinstalling the same version

### Requirement: CLI updates MUST stay separate from skill updates and vault state

The system MUST keep CLI package update behavior independent from skill-pack update behavior and per-vault campaign state.

#### Scenario: CLI update does not update skills

- **WHEN** the system applies a CLI package update
- **THEN** it MUST NOT automatically install, remove, or update the `backet` skill pack

#### Scenario: Skill update does not update CLI package

- **WHEN** a user or agent runs `backet skills update`
- **THEN** the system MUST NOT apply CLI package updates as part of that skill-pack operation

#### Scenario: CLI update does not write vault state

- **WHEN** the system checks for or applies a CLI package update
- **THEN** it MUST NOT write update metadata into `.backet/` or require a target Obsidian vault
