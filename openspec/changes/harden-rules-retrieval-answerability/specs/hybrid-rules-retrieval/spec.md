## ADDED Requirements

### Requirement: Anchored exact retrieval
Hybrid rules retrieval SHALL run anchored exact channels that require query entities and intent evidence to co-occur before using broad fallback channels.

#### Scenario: Anchored query succeeds
- **WHEN** a query has a known entity and an intent such as targeting, cost, advancement, or consequence
- **THEN** anchored channels prefer chunks where the entity and intent evidence occur in the same chunk or bounded neighbor window

#### Scenario: Broad OR result is demoted
- **WHEN** a chunk matches only one side of the query, such as only the clan name or only a generic target word
- **THEN** that chunk is demoted or rejected as a broad fallback result

### Requirement: Candidate rejection reasons
Hybrid rules retrieval SHALL include structured rejection reasons for candidates excluded from selected evidence.

#### Scenario: Candidate lacks target entity
- **WHEN** a candidate has system text but lacks the requested entity or accepted alias
- **THEN** the candidate is rejected with `missing_entity_anchor`

#### Scenario: Candidate is low-quality section
- **WHEN** a candidate comes from a character sheet, table of contents, index, art-heavy, or lore-only section for a mechanical query
- **THEN** the candidate is rejected or heavily demoted with a low-quality-section reason

### Requirement: Bounded neighbor expansion
Hybrid rules retrieval SHALL support bounded neighbor expansion around a strong anchor chunk when the answer evidence spans adjacent chunks.

#### Scenario: System text follows heading chunk
- **WHEN** a chunk contains the requested power heading and an adjacent chunk contains its system text
- **THEN** retrieval may include the adjacent chunk as selected evidence if the combined window satisfies answerability

