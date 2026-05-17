## ADDED Requirements

### Requirement: Diagnostics MUST support archetype QA grading
Answer-quality diagnostics MUST expose normalized fields needed by archetype QA, including question archetype, evidence contract ID, answerability status, source roles, satisfied facets, missing facets, selected evidence summaries, and failure-stage hints.

#### Scenario: Workbench consumes diagnostics
- **WHEN** the QA workbench evaluates an archetype case
- **THEN** it MUST be able to grade planner, retrieval, evidence, answerability, and synthesis stages without parsing human-facing Discord text except for final answer text checks

### Requirement: Diagnostics MUST identify source-role misuse
Answer-quality diagnostics MUST expose when selected evidence is an example, flavor/lore passage, specific-only mechanic, base rule, exception, or conflicting source.

#### Scenario: Specific-only answer detected
- **WHEN** selected evidence answers a base-rule question using only a specific power or example source
- **THEN** diagnostics MUST expose the source roles so archetype QA can classify the failure

### Requirement: Diagnostics MUST remain safe for QA artifacts
Answer-quality diagnostics used by archetype QA MUST avoid source PDFs, full rulebook passages, full vault sections, secrets, and unbounded prompts.

#### Scenario: QA report exported
- **WHEN** a QA report is written to disk
- **THEN** diagnostics MUST include bounded source labels, page metadata, fingerprints, and short snippets only where permitted by output policy
