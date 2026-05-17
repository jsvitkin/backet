## ADDED Requirements

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

