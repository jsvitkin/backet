## ADDED Requirements

### Requirement: Hybrid retrieval MUST support rule-unit candidates
Hybrid rules retrieval MUST be able to retrieve, rank, and return rule units alongside raw chunk candidates when rule units are available.

#### Scenario: Rule-unit channel available
- **WHEN** a rules query runs against a vault with derived rule units
- **THEN** candidate generation MUST include a rule-unit retrieval channel in addition to configured exact, semantic, metadata, and neighbor channels

#### Scenario: Rule units unavailable
- **WHEN** a rules query runs against a vault without derived rule units
- **THEN** retrieval MUST continue using the existing chunk-based channels and report that the rule-unit channel is unavailable

### Requirement: Rule-unit ranking MUST use mechanics role and facets
Hybrid retrieval MUST rank rule units using mechanics role, authority role, entity tags, answer facets, source precedence, exact matches, semantic matches, and bounded source-neighbor context.

#### Scenario: Base rule requested
- **WHEN** a user asks for a base rule and candidates include both a base-rule unit and an example or flavor unit that mentions the same term
- **THEN** retrieval MUST prefer the base-rule unit and mark the example or flavor unit as lower-authority evidence

#### Scenario: Specific mechanic requested
- **WHEN** a user asks about a named discipline power, ritual, formula, ceremony, merit, flaw, or table row
- **THEN** retrieval MUST prefer rule units tagged with that specific mechanic before broader mentions

### Requirement: Rule-unit evidence MUST remain auditable through chunks
Retrieved rule units MUST carry enough source linkage for answer stages and diagnostics to inspect the bounded source chunks that produced them.

#### Scenario: Rule unit selected as evidence
- **WHEN** retrieval selects a rule unit as answer evidence
- **THEN** the selected evidence MUST include source book, page range, heading path, unit ID, source chunk IDs, and bounded source snippets or labels
