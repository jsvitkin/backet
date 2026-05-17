## ADDED Requirements

### Requirement: Diagnostics MUST expose scenario answerability fields
Answer-quality diagnostics MUST include scenario frame, evidence contract, evidence packet, answerability status, satisfied facets, missing facets, and rejected candidate summaries for rules answers.

#### Scenario: JSON answer trace includes contract data
- **WHEN** a user or agent runs a local bot answer command in machine-readable mode
- **THEN** the trace MUST include the scenario frame, selected evidence contract, selected evidence IDs, satisfied facets, missing facets, answerability status, and bounded rejection summaries when available

#### Scenario: Human diagnostics summarize missing evidence
- **WHEN** a user runs a local playground or QA command without JSON and a rules answer is insufficient
- **THEN** the output MUST summarize the missing facets and closest source labels without printing full source passages

### Requirement: Diagnostics MUST classify scenario pipeline failures
Answer-quality diagnostics MUST identify the earliest failed stage among planning, scenario framing, contract selection, retrieval, evidence assembly, answerability, synthesis, citation, runtime, and output policy.

#### Scenario: Evidence assembly fails
- **WHEN** retrieval finds candidates but cannot assemble a packet satisfying the selected contract
- **THEN** diagnostics MUST classify the failure as evidence assembly or answerability rather than synthesis
