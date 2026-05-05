## ADDED Requirements

### Requirement: The CLI MUST support both human-friendly and agent-friendly output

The system MUST default to readable terminal output for humans while also supporting deterministic machine-readable output for agent workflows.

#### Scenario: Human-readable default output

- **WHEN** a user runs a `backet` command without requesting machine-readable output
- **THEN** the system MUST return readable terminal output intended for interactive use

#### Scenario: Deterministic agent output

- **WHEN** a user or agent requests a machine-readable format such as `--json`
- **THEN** the system MUST return deterministic structured output suitable for agent consumption

### Requirement: CLI failures MUST be actionable

The system MUST return errors that explain the problem, the scope affected, and the next recovery action where possible.

#### Scenario: Missing required context

- **WHEN** a command cannot proceed because required vault state or input is missing
- **THEN** the system MUST explain the missing requirement and suggest the next repair or setup command

#### Scenario: Unsupported command mode

- **WHEN** a command is invoked in a mode that the current vault or environment does not support
- **THEN** the system MUST explain the mismatch instead of emitting a generic failure
