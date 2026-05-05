## ADDED Requirements

### Requirement: The CLI MUST be installable from repository-hosted artifacts

The system MUST support installing `backet` from artifacts hosted by the repository and its releases without requiring a public Python package index.

#### Scenario: Install from a versioned release artifact

- **WHEN** a user installs a released version of `backet`
- **THEN** the system MUST support installation from a versioned repository-hosted artifact

#### Scenario: Upgrade from a repository-hosted artifact

- **WHEN** a user upgrades `backet` to a newer released version
- **THEN** the system MUST support upgrading from repository-hosted artifacts without requiring a package index migration

### Requirement: The install path MUST stay user-friendly

The system MUST provide a simple documented installation path that does not require users to manually clone the repository.

#### Scenario: Recommended install path

- **WHEN** a new user follows the documented install instructions
- **THEN** the system MUST provide a short install flow suitable for interactive terminal use

### Requirement: Release artifacts MUST be install-verified before publication

The system MUST validate that a release artifact can be installed and invoked successfully before it is published as a release.

#### Scenario: Verify a release candidate

- **WHEN** a release candidate artifact is built
- **THEN** the release process MUST install that artifact in a clean test environment and verify basic CLI execution before publication
