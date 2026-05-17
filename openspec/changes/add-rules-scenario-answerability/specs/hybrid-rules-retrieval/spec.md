## ADDED Requirements

### Requirement: Hybrid retrieval MUST assemble connected evidence packets
Hybrid rules retrieval MUST assemble contract-aware evidence packets from rule units, raw chunks, exact matches, semantic matches, metadata filters, and targeted neighbor expansion.

#### Scenario: Packet assembled from rule units
- **WHEN** rule units are available for a scenario-shaped query
- **THEN** retrieval MUST prefer rule units that satisfy the selected evidence contract and include linked chunks as bounded source context

#### Scenario: Packet assembled from chunks
- **WHEN** rule units are unavailable or incomplete but chunks satisfy required evidence facets
- **THEN** retrieval MUST assemble a chunk-backed evidence packet and mark the evidence source type in diagnostics

### Requirement: Evidence packet assembly MUST remain bounded
Evidence packet assembly MUST enforce configured candidate, unit, chunk, and snippet limits and MUST NOT load whole rulebooks, whole chapters, or unbounded source sections.

#### Scenario: Neighbor expansion requested
- **WHEN** a contract requires nearby context for a selected source
- **THEN** retrieval MUST expand only targeted neighbor windows within configured limits

### Requirement: Retrieval MUST expose rejected near misses
Hybrid retrieval diagnostics MUST expose bounded metadata for high-scoring candidates rejected because they did not satisfy the evidence contract.

#### Scenario: High semantic match lacks required facet
- **WHEN** a candidate scores highly but lacks a required facet such as target, cost, or restriction
- **THEN** diagnostics MUST include the rejection reason without presenting the candidate as sufficient answer evidence
