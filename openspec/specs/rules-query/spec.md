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

### Requirement: Rules queries MUST create a query plan before retrieval
The system MUST plan natural-language rules questions before retrieving rule chunks.

#### Scenario: Plan a user question
- **WHEN** a user asks a rules question through the CLI or Discord bot runtime
- **THEN** the system MUST derive a query plan containing normalized text, detected intent, canonical terms, expanded terms, retrieval queries, scope tags, and required evidence hints

#### Scenario: Preserve raw question
- **WHEN** a query plan is created
- **THEN** the plan MUST retain the raw user question for diagnostics and fallback retrieval

#### Scenario: Planning remains local
- **WHEN** a query plan is created
- **THEN** the system MUST create it locally without sending the question, rule chunks, vault content, or rulebook text to a remote service

### Requirement: Query planning MUST normalize common rules aliases
The system MUST normalize common rules aliases, compounds, plurals, and punctuation variants into canonical query terms.

#### Scenario: Compound term normalized
- **WHEN** a question contains `bloodbonds`
- **THEN** the query plan MUST include canonical and expanded terms for `blood bond` and `blood bonds`

#### Scenario: Discipline term normalized
- **WHEN** a question contains a known discipline name such as `Obfuscate`
- **THEN** the query plan MUST include the matching discipline scope tag and canonical discipline term

#### Scenario: Clan term normalized
- **WHEN** a question contains a known clan plural such as `Malkavians`
- **THEN** the query plan MUST include the matching clan scope tag and canonical clan term

### Requirement: Query planning MUST classify answer intent
The system MUST classify the kind of rules evidence needed by the question.

#### Scenario: Advancement question
- **WHEN** a question asks how a character learns or acquires a discipline or power
- **THEN** the query plan MUST mark advancement or acquisition intent and include retrieval queries for advancement rules in addition to the named discipline

#### Scenario: Targeting question
- **WHEN** a question asks whether a power can affect another type of target
- **THEN** the query plan MUST mark targeting or applicability intent and include retrieval queries for system text, target restrictions, and the named power or mechanic

#### Scenario: Definition question
- **WHEN** a question asks what a named mechanic is
- **THEN** the query plan MUST mark definition intent and prefer retrieval queries likely to find definitions over incidental mentions

### Requirement: Planned retrieval MUST reduce low-value query terms
The system MUST prevent low-value user phrasing from dominating rules retrieval.

#### Scenario: Generic verbs are downweighted
- **WHEN** a question contains generic verbs such as `use`, `make`, or `learn`
- **THEN** the query plan MUST either downweight those terms or use them only inside intent-specific retrieval queries

#### Scenario: Raw fallback is retained
- **WHEN** planned queries are generated
- **THEN** the raw query MAY remain available as a fallback, but planned canonical queries MUST be distinguishable from the raw fallback in diagnostics

### Requirement: Query plans MUST be diagnosable
The system MUST expose query planning diagnostics to local machine-readable workflows.

#### Scenario: JSON query includes plan
- **WHEN** a user or agent runs a rules query or local bot answer in JSON mode
- **THEN** the output MUST include the query plan or a diagnostic explaining why planning was unavailable

#### Scenario: Planning ambiguity detected
- **WHEN** a planner detects multiple plausible canonical meanings
- **THEN** the plan MUST include an ambiguity warning rather than silently discarding competing interpretations

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

### Requirement: Query plans preserve high-value terms
Rules query planning SHALL preserve all high-value user terms as canonical terms, accepted aliases, or raw required terms.

#### Scenario: Dementia typo is normalized
- **WHEN** a user asks whether Malkavians can use `dementia` or `dementation` on other vampires
- **THEN** the query plan includes `dementation` or an accepted equivalent and does not rely only on `malkavian`

#### Scenario: Target group remains searchable
- **WHEN** a user asks whether a power affects other vampires
- **THEN** the query plan preserves a target-group term such as `vampire`, `kindred`, or `other vampires`

### Requirement: Answerability requires entity and intent evidence
Rules query results SHALL mark a question answerable only when selected evidence contains an accepted query entity and evidence for the requested intent.

#### Scenario: Mere mention is insufficient
- **WHEN** top results mention Malkavians but do not provide system or targeting evidence for Dementation
- **THEN** the evidence packet is `insufficient` and the selected evidence list is empty

#### Scenario: Relevant system evidence is answerable
- **WHEN** results include the requested power or mechanic plus system text that addresses targeting or restrictions
- **THEN** the evidence packet is `answerable` and selected evidence includes those results

### Requirement: Fallback context is not selected evidence
Rules query output SHALL distinguish answerable selected evidence from fallback context used only for debugging or clarification.

#### Scenario: Broad fallback finds related chunks
- **WHEN** broad fallback retrieves related but incomplete chunks
- **THEN** those chunks appear in fallback context and rejected candidates, not in selected evidence

### Requirement: Degraded semantic retrieval is explicit
Rules query output SHALL report when semantic retrieval uses hash embeddings, unavailable embeddings, or a configured sentence embedding backend.

#### Scenario: Hash backend is active
- **WHEN** the rules index uses hash embeddings
- **THEN** JSON output reports semantic quality `degraded` and explains that hash embeddings are not sentence-level retrieval

### Requirement: Query reports corpus blockers
Rules query output SHALL include corpus health blockers relevant to the query, including stale metadata, missing embeddings, review exclusions, and reingest candidates.

#### Scenario: Query uses degraded corpus
- **WHEN** a query runs while the matching book has stale retrieval metadata or missing embeddings
- **THEN** JSON diagnostics include the blocker and human output suggests the repair command

### Requirement: Query planning resolves rules entities
Rules query planning SHALL resolve high-value user terms to catalog entities before candidate retrieval.

#### Scenario: Named mechanic resolved
- **WHEN** a user asks about a named mechanic such as `Blush of Life`
- **THEN** the query plan includes the resolved entity ID, canonical name, entity type, accepted aliases, and source anchors

#### Scenario: Named discipline resolved
- **WHEN** a user asks about a discipline such as `Dominate`
- **THEN** the query plan includes the discipline entity and any requested rule aspect such as targeting, cost, dice pool, or restriction

#### Scenario: Unresolved high-value term
- **WHEN** a user question contains an unknown high-value phrase that appears to be a rule name
- **THEN** the query plan preserves that phrase as unresolved and warns that retrieval cannot prove answerability from generic fallback alone

### Requirement: Query planning extracts target groups
Rules query planning SHALL extract target groups and situational constraints that affect answerability.

#### Scenario: Other vampires target group
- **WHEN** a user asks whether a power works on other vampires
- **THEN** the query plan preserves a target group such as `vampire`, `kindred`, or `other vampires`

#### Scenario: Eye contact constraint
- **WHEN** a user asks about using a power without eye contact
- **THEN** the query plan preserves `eye contact` or an accepted contact/targeting constraint as required evidence

### Requirement: Query plan exposes resolution diagnostics
Rules query planning SHALL expose entity resolution diagnostics in machine-readable output.

#### Scenario: JSON query plan returned
- **WHEN** a rules query or bot answer runs in JSON mode
- **THEN** the query plan includes resolved entities, unresolved high-value terms, target groups, alias provenance, ambiguity warnings, and resolution confidence

### Requirement: Query planning MUST include scenario-frame data
Rules query planning MUST add scenario-frame fields to the query plan for scenario-shaped rules questions.

#### Scenario: JSON query includes scenario frame
- **WHEN** a user or agent runs a rules query in machine-readable mode for a scenario-shaped question
- **THEN** the output MUST include actor, action, target, mechanic or entity, conditions, polarity, requested answer shape, frame confidence, and ambiguity warnings when available

#### Scenario: Simple definition remains simple
- **WHEN** a user asks a simple definition question that does not need a scenario frame
- **THEN** the query plan MUST either provide a minimal definition frame or explicitly mark scenario framing as not required

### Requirement: Query planning MUST select evidence contracts
Rules query planning MUST select an evidence contract that corresponds to the user's question archetype and required answer facets.

#### Scenario: Interaction contract selected
- **WHEN** a user asks how two rules, powers, or conditions interact
- **THEN** the query plan MUST select an interaction evidence contract and include retrieval hints for both mechanics and any precedence or exception evidence

#### Scenario: Contract selection unavailable
- **WHEN** the planner cannot select a reliable evidence contract
- **THEN** the query plan MUST include a diagnostic reason and downstream stages MUST treat answerability as degraded or insufficient

### Requirement: Query diagnostics MUST distinguish framing and retrieval failures
Rules query diagnostics MUST expose whether a failure occurred during scenario framing, contract selection, retrieval, evidence assembly, or synthesis.

#### Scenario: Framing failure
- **WHEN** the planner cannot identify the requested mechanic or action
- **THEN** diagnostics MUST mark the earliest failed stage as scenario framing or planning rather than retrieval

#### Scenario: Retrieval failure after valid frame
- **WHEN** the planner creates a valid scenario frame but retrieval finds no required source evidence
- **THEN** diagnostics MUST mark retrieval or evidence assembly as the failing stage and include missing facets

