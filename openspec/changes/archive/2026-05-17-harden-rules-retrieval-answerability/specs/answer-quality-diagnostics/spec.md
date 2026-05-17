## ADDED Requirements

### Requirement: False-confidence diagnostics
Answer diagnostics SHALL expose why evidence was considered answerable or insufficient, including entity anchors, intent evidence, semantic quality, and candidate rejection reasons.

#### Scenario: Answerability fails
- **WHEN** the rules evidence packet is insufficient
- **THEN** diagnostics include missing entity or intent evidence and a bounded list of rejected candidates

#### Scenario: Degraded retrieval answers
- **WHEN** a lite profile answers using degraded semantic retrieval
- **THEN** diagnostics include a warning that the answer was produced without sentence-level semantic retrieval

