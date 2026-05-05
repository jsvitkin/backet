## ADDED Requirements

### Requirement: Derived memory MUST remain subordinate to canonical notes

The system MUST treat human-authored vault notes as the canonical source of campaign truth and derived memory as rebuildable support material.

#### Scenario: Rebuild memory after canon changes

- **WHEN** canonical notes change
- **THEN** the system MUST allow derived memory artifacts to be regenerated from those notes

### Requirement: Derived memory MUST be persisted as readable scoped capsules

The system MUST persist readable memory capsules under `.backet/` for scopes that are useful to both humans and agents.

#### Scenario: Build memory capsules

- **WHEN** derived memory is generated or refreshed
- **THEN** the system MUST write scoped readable artifacts under `.backet/` rather than keeping them only in opaque machine state

#### Scenario: Trace memory back to canon

- **WHEN** a user or agent inspects a derived memory capsule
- **THEN** the system MUST preserve enough source reference information to understand where the memory came from

### Requirement: Missing or outdated memory MUST be recoverable

The system MUST detect when derived memory is absent or outdated and provide a rebuild path.

#### Scenario: Recover missing derived memory

- **WHEN** a requested memory capsule is missing or stale
- **THEN** the system MUST offer or perform a rebuild path instead of failing without guidance
