# rules-query Specification

## Purpose
TBD - created by archiving change add-rules-pdf-ingestion. Update Purpose after archive.
## Requirements
### Requirement: Rules queries MUST return raw chunks with source metadata

The system MUST expose raw ingested rule chunks as the primary retrieval output for this change.

#### Scenario: Request rules in machine-readable form

- **WHEN** a user or agent requests rule retrieval in a machine-readable mode
- **THEN** the system MUST return raw chunks together with source metadata needed to inspect and attribute the result

### Requirement: Rules queries MUST apply precedence between core and specific sources

The system MUST prefer more specific rule sources over core rule sources when both match the same query area.

#### Scenario: Prefer a supplement-specific rule over core fallback

- **WHEN** a query matches both a core rule and a more specific supplement rule
- **THEN** the system MUST prioritize the more specific rule while keeping the core rule available as fallback context

### Requirement: Rules queries MUST surface ambiguous specific-rule conflicts

The system MUST not silently resolve conflicts between multiple specific rule sources.

#### Scenario: Conflicting specific sources

- **WHEN** two or more specific rule sources conflict for the same rule area
- **THEN** the system MUST surface the ambiguity and require user choice or explicit follow-up instead of auto-resolving it

