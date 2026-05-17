# answer-quality-diagnostics Specification

## Purpose
TBD - created by archiving change add-answer-quality-diagnostics. Update Purpose after archive.
## Requirements
### Requirement: Bot answer traces MUST expose stage-aware diagnostics
The system MUST expose a structured answer trace for local bot answer workflows so users and agents can identify whether a bad answer came from retrieval, answerability, or answer generation.

#### Scenario: JSON bot answer includes trace
- **WHEN** a user or agent runs a local bot answer command in machine-readable mode
- **THEN** the response MUST include a diagnostic trace with command route, access tier, retrieval attempts, retrieval errors, selected source metadata, answer generation mode, fallback status, response size, and a stable trace schema version

#### Scenario: Trace preserves privacy boundaries
- **WHEN** a diagnostic trace includes retrieved source material
- **THEN** the trace MUST include only bounded snippets and source metadata and MUST NOT include source PDFs, full rulebooks, full vault sections, Discord tokens, SSH keys, or model-download credentials

#### Scenario: Future stages are absent
- **WHEN** query planning, reranking, or answerability gates are not yet implemented
- **THEN** the trace MUST make those stages explicitly absent or unavailable instead of inventing successful diagnostics

### Requirement: Bot playground MUST support human answer debugging
The system MUST provide concise human-readable answer diagnostics through the local playground workflow.

#### Scenario: Playground shows source ranking
- **WHEN** a user runs the bot playground for a rules question
- **THEN** the output MUST show the generated answer, selected source labels, source scores, match reasons, retrieval mode, and any retrieval or generation warnings

#### Scenario: Playground output remains bounded
- **WHEN** playground diagnostics display retrieved source text
- **THEN** the output MUST keep snippets bounded and MUST NOT print entire books, entire vault sections, or raw source PDFs

### Requirement: Answer-quality regression cases MUST be executable
The system MUST support executable regression cases for bot answer quality.

#### Scenario: Run regression case set
- **WHEN** the automated test suite runs answer-quality cases
- **THEN** each case MUST execute the local bot runtime against a deterministic fixture corpus or bundle and report retrieval, answerability, and answer text status separately

#### Scenario: Assert expected evidence
- **WHEN** a regression case defines expected source books, pages, paths, or section labels
- **THEN** the evaluator MUST fail the retrieval stage if the selected answer sources do not satisfy those expectations

#### Scenario: Assert forbidden evidence
- **WHEN** a regression case defines forbidden source books, pages, paths, section labels, or text patterns
- **THEN** the evaluator MUST fail the retrieval stage if selected answer sources match the forbidden evidence

#### Scenario: Assert insufficiency
- **WHEN** a regression case declares that available fixture sources are insufficient
- **THEN** the evaluator MUST fail the answerability or answer stage if the bot presents an unsupported answer as sufficient

### Requirement: Diagnostics MUST be useful across answer modes
The diagnostic system MUST work for template answers and model-generated answers.

#### Scenario: Template answer traced
- **WHEN** the bot answers through deterministic template mode
- **THEN** the trace MUST identify template mode and include the selected source snippets used by that formatter

#### Scenario: Model answer traced
- **WHEN** the bot answers through local model synthesis
- **THEN** the trace MUST identify model mode, fallback status, validation status, and the source labels supplied to the model without exposing secrets or unbounded prompts in normal diagnostics

### Requirement: QA-consumable answer diagnostics
Answer diagnostics SHALL expose normalized fields for planner terms, retrieval mode, semantic quality, evidence status, selected source anchors, answer mode, fallback reason, and response class.

#### Scenario: Workbench reads diagnostics
- **WHEN** the QA workbench evaluates a bot answer
- **THEN** it can classify the answer without parsing human-facing Discord text except for final answer pattern checks

### Requirement: Failure reasons remain paste-safe
Answer diagnostics SHALL avoid raw source PDF paths, secrets, full source passages, Discord tokens, and unbounded user text.

#### Scenario: Diagnostic report is shared
- **WHEN** a user shares a QA failure report
- **THEN** the report contains source labels, page metadata, fingerprints, and bounded snippets only

### Requirement: False-confidence diagnostics
Answer diagnostics SHALL expose why evidence was considered answerable or insufficient, including entity anchors, intent evidence, semantic quality, and candidate rejection reasons.

#### Scenario: Answerability fails
- **WHEN** the rules evidence packet is insufficient
- **THEN** diagnostics include missing entity or intent evidence and a bounded list of rejected candidates

#### Scenario: Degraded retrieval answers
- **WHEN** a lite profile answers using degraded semantic retrieval
- **THEN** diagnostics include a warning that the answer was produced without sentence-level semantic retrieval

### Requirement: Synthesis diagnostics
Answer diagnostics SHALL include the answer outline, selected evidence IDs, final synthesis mode, validation status, and fallback reason.

#### Scenario: Model validation fails
- **WHEN** local model output is rejected
- **THEN** diagnostics include the validation error code and the fallback policy used

#### Scenario: Deterministic composer answers
- **WHEN** the deterministic composer produces the final answer
- **THEN** diagnostics identify the answer shape and source IDs used for each claim

### Requirement: Unsupported claim checks
Answer diagnostics SHALL expose whether final text claims are supported by selected evidence.

#### Scenario: Forbidden pattern detected
- **WHEN** final text matches a QA forbidden pattern for the case
- **THEN** the workbench can classify the failure as synthesis rather than retrieval

