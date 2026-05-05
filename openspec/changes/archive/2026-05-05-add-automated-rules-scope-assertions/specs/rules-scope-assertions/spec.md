## ADDED Requirements

### Requirement: Rules ingest MUST generate local scope assertions
The system MUST generate scope assertions for ingested rulebook spans using local source structure, vocabulary, and content signals without requiring the user to manually define complete scope tags.

#### Scenario: Ingest generates assertions from structured source
- **WHEN** a user ingests a rulebook PDF with a table of contents, page headings, or section labels
- **THEN** the system MUST generate scope assertions for detected book, page, section, or chunk spans
- **AND** each assertion MUST include normalized tags, span metadata, role, confidence, status, and evidence

#### Scenario: Ingest remains local
- **WHEN** the system generates scope assertions during rules ingestion
- **THEN** the system MUST NOT send rulebook text, extracted chunks, scope assertions, or embeddings to a remote service

#### Scenario: Ingest requires no manual scope tags
- **WHEN** a user ingests a rulebook PDF
- **THEN** the system MUST NOT require manual source-scope or scope-tag input
- **AND** the system MUST infer source and span scope assertions automatically where source structure or content evidence supports them

### Requirement: Scope assertions MUST distinguish authority roles
The system MUST classify scope assertions by role so retrieval can distinguish authoritative rules from mentions or in-world perspectives.

#### Scenario: Mechanical authority span
- **WHEN** a span contains mechanics for a detected topic such as clan rules, rituals, loresheets, or a named conflict system
- **THEN** the generated assertion MUST be able to mark the span as mechanical authority for the relevant normalized tags

#### Scenario: Perspective span
- **WHEN** a span discusses a topic from another source's in-world perspective without providing authoritative mechanics for that topic
- **THEN** the generated assertion MUST be able to mark the span as perspective or mention
- **AND** that assertion MUST NOT by itself establish supplement precedence over a mechanically authoritative source

### Requirement: Scope assertions MUST use a controlled typed vocabulary
The system MUST normalize generated and user-supplied scope tags through a controlled typed vocabulary with aliases.

#### Scenario: Canonicalize aliases
- **WHEN** source structure or content contains an alias such as "Children of Haqim", "Assamite", or "Ivory Tower"
- **THEN** the system MUST normalize the assertion to the configured canonical tag such as `clan:banu-haqim` or `sect:camarilla`

#### Scenario: Preserve unknown suggestions
- **WHEN** the generator detects a plausible scope that does not match the controlled vocabulary
- **THEN** the system MUST preserve the suggestion with evidence
- **AND** the system MUST NOT use that unknown suggestion for authoritative precedence unless it is reviewed or normalized

#### Scenario: Limit initial taxonomy to Vampire
- **WHEN** the system ships its initial controlled scope vocabulary
- **THEN** the vocabulary MUST focus on Vampire: The Masquerade tags and aliases
- **AND** the vocabulary MUST NOT attempt to classify unrelated World of Darkness game lines unless needed for a Vampire source cross-reference

### Requirement: Scope assertions MUST be persisted with the rules corpus
The system MUST persist generated and reviewed scope assertions in per-vault rules state so they travel with the ingested rules corpus.

#### Scenario: Store assertion data
- **WHEN** rules ingestion generates scope assertions
- **THEN** the system MUST store the assertions under the target vault's `.backet/rules/` state
- **AND** the stored data MUST be associated with the relevant book and span without copying the source PDF into the vault

#### Scenario: Preserve assertion evidence
- **WHEN** an assertion is stored
- **THEN** the system MUST preserve evidence sufficient to explain why the assertion was generated
- **AND** machine-readable output MUST expose that evidence for audit or agent review

#### Scenario: Export manifest on demand
- **WHEN** scope assertions are generated during ingestion
- **THEN** the system MUST keep SQLite rules state as the canonical persisted assertion source
- **AND** the system MUST NOT require a default YAML manifest file to be written for every ingested book

### Requirement: Rules queries MUST use applied chunk scopes for precedence
The system MUST use applied high-confidence scope assertions when filtering, ranking, and applying supplement precedence for rules queries.

#### Scenario: Query matches a chunk-level authority scope
- **WHEN** a query includes a scope tag that matches an applied authoritative assertion on a supplement chunk
- **THEN** the system MUST allow that chunk to satisfy supplement-specific precedence for the requested scope
- **AND** the query result MUST report the matched scope assertion or match reason in machine-readable output

#### Scenario: Query matches only a perspective scope
- **WHEN** a query includes a scope tag that matches only perspective or mention assertions in a supplement
- **THEN** the system MUST be able to retrieve those chunks as contextual results
- **AND** the system MUST NOT treat those chunks as mechanically authoritative fallback replacements for a dedicated authoritative source

#### Scenario: No chunk scope exists
- **WHEN** a matching chunk has no applied scope assertion
- **THEN** the system MAY fall back to migrated book-level source-scope hints from older ingests
- **AND** machine-readable output MUST indicate that source-level fallback was used

### Requirement: Scope assertion confidence MUST control automatic application
The system MUST apply generated scope assertions according to implementation-owned confidence bands rather than requiring users to choose thresholds.

#### Scenario: High-confidence assertion
- **WHEN** a generated assertion has confidence greater than or equal to the configured auto-apply threshold
- **THEN** the system MUST apply it to the affected chunks unless validation rejects its tag, role, or span

#### Scenario: Medium-confidence assertion
- **WHEN** a generated assertion has confidence below the auto-apply threshold but greater than or equal to the configured suggestion threshold
- **THEN** the system MUST store it as a suggestion
- **AND** the system MUST NOT use it for authoritative precedence until reviewed or promoted

#### Scenario: Low-confidence assertion
- **WHEN** a generated assertion has confidence below the configured suggestion threshold
- **THEN** the system MUST NOT use it for authoritative precedence

### Requirement: Users and agents MUST be able to inspect and revise scopes
The system MUST provide deterministic CLI surfaces for inspecting generated assertions and applying reviewed corrections.

#### Scenario: Audit generated scopes
- **WHEN** a user or agent audits scopes for an ingested book
- **THEN** the system MUST return a bounded summary of source scope, applied assertions, suggested assertions, rejected assertions, review-needed spans, and confidence distribution

#### Scenario: Export generated scopes
- **WHEN** a user or agent exports scope assertions for an ingested book
- **THEN** the system MUST produce an inspectable machine-readable manifest containing assertion spans, tags, roles, statuses, confidence, and evidence

#### Scenario: Apply reviewed scopes
- **WHEN** a user or agent applies a reviewed scope manifest
- **THEN** the system MUST validate normalized tags, spans, roles, and statuses before updating durable rules state
- **AND** the system MUST refresh affected retrieval metadata so subsequent queries use the reviewed scopes
