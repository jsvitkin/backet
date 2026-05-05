# context-bundles Specification

## Purpose
TBD - created by archiving change add-hybrid-retrieval-and-vault-memory. Update Purpose after archive.
## Requirements
### Requirement: Context retrieval MUST return bounded scope-aware bundles

The system MUST assemble bounded context bundles from the indexed vault instead of dumping broad sections of the vault directly into model context.

#### Scenario: Retrieve narrow local context

- **WHEN** a user or agent requests context for a narrow scope such as a note, subtree, or local plotline
- **THEN** the system MUST return a bounded bundle focused on that scope and its most relevant supporting material

#### Scenario: Retrieve broad campaign context

- **WHEN** a user or agent requests broader campaign-level context
- **THEN** the system MUST assemble that context from across the indexed vault while still returning a bounded response rather than raw whole-vault output

### Requirement: Context retrieval MUST use hybrid ranking

The system MUST combine exact search, semantic retrieval, metadata filters, and hierarchy-aware expansion when assembling context bundles.

#### Scenario: Resolve an exact canon lookup

- **WHEN** a query targets an exact named entity, note title, or known term
- **THEN** the system MUST be able to prioritize exact and metadata-aware matches over merely similar prose

#### Scenario: Resolve a semantic campaign query

- **WHEN** a query is conceptual or thematic rather than an exact title match
- **THEN** the system MUST be able to use semantic retrieval and hierarchy-aware expansion to assemble relevant context

### Requirement: Context bundles MUST support deterministic agent output

The system MUST expose a machine-readable mode for context-bundle retrieval.

#### Scenario: Request JSON context

- **WHEN** a user or agent requests a machine-readable context bundle
- **THEN** the system MUST return deterministic structured output that includes scope and source information

