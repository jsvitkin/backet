## ADDED Requirements

### Requirement: Grounded answer outlines
The bot SHALL build a grounded answer outline from selected evidence before producing final Discord prose.

#### Scenario: Direct yes/no question
- **WHEN** selected evidence answers whether a rule applies to a target
- **THEN** the outline includes a stance, supporting source IDs, and any stated restrictions

#### Scenario: Evidence is insufficient
- **WHEN** the answer packet is insufficient, ambiguous, conflicting, permission-denied, or runtime-unavailable
- **THEN** the bot does not produce a substantive answer and instead emits the appropriate non-answer response

### Requirement: Selected evidence only
Rules answer synthesis SHALL use selected evidence for claims and citations, not fallback context or rejected candidates.

#### Scenario: Fallback context exists
- **WHEN** fallback context contains related chunks but the evidence packet is insufficient
- **THEN** synthesis abstains and does not cite fallback context as if it were selected evidence

### Requirement: Source-grounded final answers
Final Discord answers SHALL include a direct answer first, cite source labels once, and avoid unsupported claims.

#### Scenario: Model output lacks citation
- **WHEN** model-generated text omits required source citation or cites an unavailable source
- **THEN** validation rejects it and the configured fallback policy is applied

#### Scenario: Template fallback runs
- **WHEN** deterministic fallback is allowed
- **THEN** fallback output uses the answer outline and selected evidence rather than raw first-source sentence picking

### Requirement: Quality profile fallback behavior
Bot synthesis SHALL respect runtime profile fallback policy.

#### Scenario: Quality profile model unavailable
- **WHEN** the quality profile requires local model synthesis and the model is unavailable
- **THEN** the bot fails closed with a runtime-unavailable answer instead of silently using low-quality template synthesis

