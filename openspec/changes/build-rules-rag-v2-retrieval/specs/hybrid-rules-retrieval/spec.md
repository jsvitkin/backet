## ADDED Requirements

### Requirement: Rules retrieval MUST produce a staged evidence packet
The system MUST retrieve rules through a staged RAG pipeline that separates candidate generation, reranking, evidence gating, and final source selection.

#### Scenario: RAG v2 query returns evidence packet
- **WHEN** a rules query is executed with RAG v2 retrieval available
- **THEN** the machine-readable response MUST include an evidence packet containing selected evidence, fallback context, rejected high-scoring candidates, evidence status, candidate counts, and retrieval diagnostics

#### Scenario: Existing result fields retained
- **WHEN** RAG v2 retrieval returns results during the transition period
- **THEN** the response MUST continue to expose primary and fallback result fields or a documented compatibility equivalent for existing callers

### Requirement: Candidate generation MUST use planned retrieval channels
The system MUST gather candidates from multiple bounded retrieval channels derived from the query plan.

#### Scenario: Planned exact candidates
- **WHEN** a query plan contains canonical terms and aliases
- **THEN** candidate generation MUST run exact or phrase retrieval for those planned terms

#### Scenario: Semantic candidates
- **WHEN** compatible semantic embeddings are available
- **THEN** candidate generation MUST include semantic candidates and report the embedding backend and model used

#### Scenario: Raw fallback candidates
- **WHEN** planned retrieval is available
- **THEN** candidate generation MAY include raw query fallback candidates but MUST mark them separately from planned candidates in diagnostics

### Requirement: RAG v2 MUST rerank candidates before source selection
The system MUST rerank candidates against the query plan before selecting answer sources.

#### Scenario: Intent-aware reranking
- **WHEN** the query plan marks advancement intent
- **THEN** reranking MUST prefer chunks with advancement, acquisition, prerequisite, or learning-rule evidence over chunks that merely mention the named discipline

#### Scenario: Targeting-aware reranking
- **WHEN** the query plan marks targeting or applicability intent
- **THEN** reranking MUST prefer chunks with system text, target restrictions, or applicability evidence over lore-only mentions

#### Scenario: Definition-aware reranking
- **WHEN** the query plan marks definition intent
- **THEN** reranking MUST prefer definition or explanatory chunks over incidental mentions or activation costs

### Requirement: RAG v2 MUST gate answerability
The system MUST classify whether selected evidence can answer the planned question.

#### Scenario: Evidence is sufficient
- **WHEN** selected chunks satisfy the required evidence hints in the query plan
- **THEN** the evidence packet MUST mark the query as answerable

#### Scenario: Evidence is only a mention
- **WHEN** selected chunks mention the requested entity but do not satisfy the required evidence hints
- **THEN** the evidence packet MUST mark the query as insufficient and include the missing evidence type

#### Scenario: Comparable sources conflict
- **WHEN** selected answerable chunks from comparable authoritative sources conflict or have comparable precedence
- **THEN** the evidence packet MUST mark the query as ambiguous or conflicting rather than silently selecting one source

### Requirement: Semantic quality MUST be explicit
The system MUST report whether semantic retrieval used a production-quality embedding backend or a degraded fallback.

#### Scenario: Hash backend used
- **WHEN** semantic retrieval uses the hash embedding backend
- **THEN** diagnostics MUST report degraded semantic quality and MUST NOT present the result as equivalent to sentence-level semantic retrieval

#### Scenario: Semantic backend unavailable
- **WHEN** a compatible semantic backend is unavailable
- **THEN** retrieval MUST fall back to exact and metadata-aware channels and report that semantic retrieval was unavailable
