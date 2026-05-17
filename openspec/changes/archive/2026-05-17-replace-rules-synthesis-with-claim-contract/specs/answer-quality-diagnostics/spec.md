## ADDED Requirements

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
