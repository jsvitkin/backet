## ADDED Requirements

### Requirement: Local rules entity catalog
The system SHALL maintain a local, rebuildable catalog of rules entities derived from ingested rule blocks and curated seed aliases.

#### Scenario: Catalog entry generated
- **WHEN** indexing sees a structured rule block for a named mechanic, discipline, power, ritual, ceremony, formula, clan, predator type, or target group
- **THEN** it creates or updates a catalog entry with canonical name, entity type, aliases, source block anchors, source pages, scope tags, and provenance

#### Scenario: Curated seed alias applied
- **WHEN** a user asks for a common alias or phrase such as `Blush of Life`, `Rouse Check`, or a discipline power spelling variant
- **THEN** the resolver can match it through curated seed aliases even before a generated alias is perfect

#### Scenario: Catalog remains local
- **WHEN** the catalog is built or refreshed
- **THEN** rulebook text and generated aliases remain in local per-vault state and are not sent to remote services

### Requirement: Alias provenance and ambiguity
The rules entity catalog SHALL retain enough provenance to detect alias collisions and ambiguous rule references.

#### Scenario: Alias maps to multiple entities
- **WHEN** the same alias plausibly matches multiple comparable catalog entries
- **THEN** resolution returns an ambiguity diagnostic instead of silently choosing one

#### Scenario: Alias source is inspected
- **WHEN** JSON diagnostics include a resolved entity
- **THEN** they include whether the match came from curated seed data, heading text, body text, exact user text, or generated aliases

### Requirement: Incremental catalog rebuild
The rules entity catalog SHALL refresh incrementally based on source block content hashes and catalog schema version.

#### Scenario: Block unchanged
- **WHEN** a rule block content hash and catalog schema version are current
- **THEN** indexing reuses the existing catalog entry

#### Scenario: Block changed
- **WHEN** a rule block text, heading path, or alias metadata changes
- **THEN** indexing refreshes affected catalog entries and reports updated counts
