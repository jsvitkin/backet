## ADDED Requirements

### Requirement: The CLI MUST scaffold named workflow blueprints

The system MUST provide a deterministic CLI command that applies a named workflow blueprint to a bootstrapped vault by creating or preparing the blueprint's expected note targets and metadata.

#### Scenario: Apply the default city blueprint

- **WHEN** a user runs the blueprint apply command for `city-by-night-v1`
- **THEN** the CLI MUST create or prepare the default note targets and committed blueprint metadata required for workflow inspection

### Requirement: The CLI MUST support partial slot remapping with default fallback

The system MUST allow users to override the note path for specific semantic slots while continuing to use blueprint defaults for every slot that has not been explicitly remapped.

#### Scenario: Customize one slot and inherit the rest

- **WHEN** a user explicitly remaps one or more semantic slots away from the blueprint default layout
- **THEN** the CLI MUST preserve those custom mappings and continue to resolve all untouched slots from the blueprint defaults

### Requirement: The CLI MUST report blueprint status in human-friendly and machine-readable forms

The system MUST provide blueprint status reporting that shows which semantic slots are present, which are missing, and which gaps are next in priority, with deterministic structured output available for agent workflows.

#### Scenario: Inspect blueprint status for agent use

- **WHEN** a user or skill requests blueprint status with a machine-readable mode such as `--json`
- **THEN** the CLI MUST return deterministic structured data including blueprint identity, slot status, and the next highest-priority missing targets

### Requirement: Blueprint scaffolding MUST be non-destructive

Applying a blueprint MUST not overwrite existing canonical note content silently.

#### Scenario: Re-apply an existing blueprint

- **WHEN** a user applies a blueprint whose target notes already exist
- **THEN** the CLI MUST preserve existing canonical note content and report the existing targets instead of overwriting them silently

### Requirement: Blueprint state MUST be committed and portable

Workflow blueprint metadata MUST live in committed per-vault state so the same vault can be reopened on another machine without losing structural workflow context.

#### Scenario: Reopen a blueprinted vault on another machine

- **WHEN** a bootstrapped vault with applied workflow blueprints is reopened on a different machine
- **THEN** the system MUST be able to recover blueprint identity and slot mappings from committed state under `.backet/` without relying on machine-local scratch artifacts
