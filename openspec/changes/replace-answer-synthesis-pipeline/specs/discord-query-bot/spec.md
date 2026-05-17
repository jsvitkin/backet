## ADDED Requirements

### Requirement: Bot answer synthesis MUST be evidence-aware
The bot MUST choose answer behavior from vetted evidence status rather than from raw source overlap alone.

#### Scenario: Evidence supports answer
- **WHEN** retrieval returns evidence marked answerable for the planned question
- **THEN** the bot MUST produce a compact answer grounded only in the selected evidence and cite the relevant sources

#### Scenario: Evidence is insufficient
- **WHEN** retrieval returns sources that mention query terms but do not satisfy the required evidence
- **THEN** the bot MUST say that the permitted sources are insufficient instead of presenting the mention as an answer

#### Scenario: Evidence is ambiguous
- **WHEN** retrieval reports multiple comparable authoritative sources or an ambiguity requiring a narrower scope
- **THEN** the bot MUST ask for a narrower book, scope, clan, discipline, or Storyteller decision rather than silently choosing one

#### Scenario: Evidence conflicts
- **WHEN** retrieval reports conflicting evidence
- **THEN** the bot MUST identify that the permitted sources conflict and MUST NOT invent a reconciliation

### Requirement: Template fallback MUST honor evidence status
Template answer mode MUST remain available but MUST be driven by evidence status.

#### Scenario: Template answer from answerable evidence
- **WHEN** template mode receives answerable evidence
- **THEN** it MUST format a concise answer and source detail from selected evidence

#### Scenario: Template refusal from insufficient evidence
- **WHEN** template mode receives insufficient evidence
- **THEN** it MUST return a concise insufficiency message with closest-source diagnostics only in local debug surfaces

#### Scenario: Template ambiguity response
- **WHEN** template mode receives ambiguous or conflicting evidence
- **THEN** it MUST return a concise narrowing or conflict message and preserve source references where safe

### Requirement: Model synthesis MUST be bounded by evidence
Optional model-generated answers MUST use only permitted evidence supplied by the runtime.

#### Scenario: Model prompt receives answer packet
- **WHEN** model synthesis is enabled and evidence is answerable
- **THEN** the model prompt MUST include only the question, answer-shape instructions, selected permitted evidence, and source labels needed for citation

#### Scenario: Model cannot override insufficiency
- **WHEN** evidence status is insufficient
- **THEN** model synthesis MUST NOT turn the response into a substantive answer unless new authorized evidence is retrieved by an allowed retrieval path

#### Scenario: Model output lacks grounding
- **WHEN** model output omits required citations, cites unavailable sources, exceeds response limits, or violates evidence status
- **THEN** the bot MUST repair the response, fall back to evidence-aware template mode, or refuse

### Requirement: Discord answer formatting MUST remain compact and safe
The bot MUST format evidence-aware responses for Discord without leaking hidden content or triggering unwanted mentions.

#### Scenario: Answer fits Discord
- **WHEN** an answer and source detail fit within Discord limits
- **THEN** the bot MUST send a compact response with direct answer first and source detail after it

#### Scenario: Answer needs splitting
- **WHEN** an answer exceeds safe Discord message limits
- **THEN** the bot MUST split or shorten the response while preserving source references and evidence status

#### Scenario: Retrieved text contains mentions
- **WHEN** retrieved source text or user input contains Discord mention syntax
- **THEN** the bot MUST sanitize the response and use allowed-mentions controls to prevent unwanted mentions
