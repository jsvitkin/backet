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

### Requirement: QA-normalized trace fields
Answer diagnostics SHALL expose normalized fields that allow the QA workbench to evaluate each pipeline stage without parsing human prose except for final answer text assertions.

#### Scenario: QA evaluates retrieval
- **WHEN** a QA case checks selected evidence anchors
- **THEN** the answer trace exposes selected evidence labels, book IDs, page ranges, section labels, canonical entity anchors, match reasons, and rejection reasons

#### Scenario: QA evaluates synthesis
- **WHEN** a QA case checks final answer support
- **THEN** the answer trace exposes response class, answerability status, synthesis mode, fallback reason, cited source IDs, and final answer text

#### Scenario: QA evaluates model fallback
- **WHEN** model synthesis is attempted
- **THEN** the answer trace exposes model ID, validation status, validation error code, and whether fallback output became the visible answer

### Requirement: Report-safe failure context
Answer diagnostics SHALL provide enough bounded context for QA reports to explain failures without leaking full source material or secrets.

#### Scenario: Failure report generated
- **WHEN** a QA report includes failed stage details
- **THEN** it includes source labels, page metadata, stable fingerprints, and bounded snippets but excludes raw PDFs, full rulebook text, Discord tokens, model prompts, and private file paths unless explicitly requested in local debug mode

### Requirement: Entity resolution trace
Answer diagnostics SHALL expose entity resolution and target-first retrieval decisions for local bot answers and QA reports.

#### Scenario: Bot answer includes trace
- **WHEN** a local bot answer runs in JSON mode
- **THEN** the answer trace includes resolved entities, unresolved high-value terms, target groups, alias provenance, entity-first retrieval mode, and answerability gate results

#### Scenario: Resolution fails
- **WHEN** a bot answer abstains because a high-value term could not be resolved
- **THEN** diagnostics identify the unresolved term and closest catalog or fallback matches without presenting fallback matches as answer evidence

### Requirement: Claim synthesis diagnostics
Answer diagnostics SHALL expose claim extraction and validation details for each answer attempt.

#### Scenario: Claims extracted
- **WHEN** synthesis extracts one or more claims
- **THEN** diagnostics include claim IDs, claim text, source IDs, covered intents, stance, support status, validation errors, and final composer usage

#### Scenario: Claim extraction fails
- **WHEN** selected evidence exists but no valid claim can be extracted
- **THEN** diagnostics identify missing claim coverage separately from retrieval and answerability failures

#### Scenario: Model-assisted claim rejected
- **WHEN** a local model-proposed claim is rejected
- **THEN** diagnostics include the rejection code without exposing full prompts or unbounded source text

### Requirement: Final answer support report
Answer diagnostics SHALL report whether each final answer sentence or bullet is backed by a validated claim.

#### Scenario: Final answer generated
- **WHEN** the bot produces a substantive final answer
- **THEN** diagnostics map each final answer bullet or sentence to at least one validated claim and source ID

#### Scenario: Unsupported final answer blocked
- **WHEN** a final answer sentence lacks a supporting validated claim
- **THEN** validation blocks the answer or removes the unsupported sentence before user-visible output

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

