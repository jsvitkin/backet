## ADDED Requirements

### Requirement: Skills MUST be installable independently from the CLI package

The system MUST support installing the `backet` skill pack without requiring the skills to be bundled directly into a target vault.

#### Scenario: Install skills after CLI installation

- **WHEN** a user has the `backet` CLI installed on a machine
- **THEN** the system MUST support installing the associated skill pack separately from that machine-level CLI installation

### Requirement: Skills MUST be updateable independently from CLI releases

The system MUST support checking and applying skill updates without requiring every skill update to coincide with a CLI package upgrade.

#### Scenario: Update skills without changing CLI version

- **WHEN** a newer compatible skill pack is available than the one currently installed
- **THEN** the system MUST support updating the skills without requiring a CLI package reinstall

#### Scenario: Handle incompatibility between CLI and skills

- **WHEN** a requested skill pack version is incompatible with the installed CLI
- **THEN** the system MUST report the incompatibility and guide the user toward a compatible upgrade path

### Requirement: Installed skills MUST remain compliant with Codex skill conventions

The system MUST treat the skill pack as an Agent Skills-compatible artifact and preserve the metadata and file structure required for Codex discovery and execution.

#### Scenario: Install a skill pack

- **WHEN** the system installs or updates the `backet` skills
- **THEN** it MUST preserve the skill structure and metadata required by current OpenAI/Codex skill conventions
