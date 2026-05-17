## ADDED Requirements

### Requirement: Query reports corpus blockers
Rules query output SHALL include corpus health blockers relevant to the query, including stale metadata, missing embeddings, review exclusions, and reingest candidates.

#### Scenario: Query uses degraded corpus
- **WHEN** a query runs while the matching book has stale retrieval metadata or missing embeddings
- **THEN** JSON diagnostics include the blocker and human output suggests the repair command

