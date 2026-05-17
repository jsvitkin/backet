## ADDED Requirements

### Requirement: Rules query output MUST expose RAG v2 diagnostics
The system MUST expose deterministic diagnostics for the RAG v2 retrieval pipeline.

#### Scenario: Query returns candidate counts
- **WHEN** a rules query uses RAG v2 retrieval
- **THEN** the machine-readable output MUST report candidate counts by retrieval channel, reranked candidate counts, evidence status, and selected evidence count

#### Scenario: Query reports rejected candidates
- **WHEN** high-scoring candidates are rejected by reranking or answerability gating
- **THEN** diagnostics MUST include bounded metadata and rejection reasons for those candidates

#### Scenario: Query reports missing evidence
- **WHEN** the evidence gate marks a query insufficient
- **THEN** diagnostics MUST identify the missing evidence type and the closest selected sources without presenting them as sufficient answer evidence

### Requirement: Rules queries MUST remain bounded
The system MUST keep RAG v2 retrieval bounded even when candidate generation uses multiple channels.

#### Scenario: Candidate cap enforced
- **WHEN** RAG v2 candidate generation runs
- **THEN** the system MUST enforce configured candidate and context limits rather than loading whole rulebooks or unbounded sections

#### Scenario: Source text remains inspectable
- **WHEN** query output includes selected evidence
- **THEN** it MUST include source metadata and bounded chunks or excerpts sufficient for attribution and debugging
