## ADDED Requirements

### Requirement: Supported answer claims
The system SHALL represent substantive rules answers as supported claims before composing final user-facing text.

#### Scenario: Claim extracted
- **WHEN** selected evidence directly answers the planned question
- **THEN** synthesis creates a claim with text, source IDs, support spans or windows, covered entity IDs, covered intent, stance when applicable, target constraints when applicable, and validation status

#### Scenario: No direct claim
- **WHEN** selected evidence is related but no claim covers the planned entity, intent, and constraints
- **THEN** synthesis marks the answer insufficient and does not produce a substantive final answer

#### Scenario: Multiple claims needed
- **WHEN** a correct answer requires multiple supported facts such as cost plus consequence
- **THEN** the claim set preserves each fact with its own support and the final answer cites all used sources

### Requirement: Claim validation
The system SHALL validate answer claims against selected evidence before final composition.

#### Scenario: Unsupported claim rejected
- **WHEN** a claim cannot be grounded in selected evidence by source ID and support span or normalized support terms
- **THEN** validation rejects the claim and records the missing support reason

#### Scenario: Wrong stance rejected
- **WHEN** a yes/no claim stance conflicts with the selected evidence or planned answer stance
- **THEN** validation rejects the claim before final composition

#### Scenario: Fallback context ignored
- **WHEN** fallback context contains a tempting answer but selected evidence is insufficient
- **THEN** claim validation does not allow fallback context to support a substantive answer

### Requirement: Claim-based final composer
The system SHALL compose deterministic fallback answers from validated claims rather than raw best-matching sentences.

#### Scenario: Validated claim available
- **WHEN** one or more validated claims cover the question
- **THEN** the deterministic composer emits a direct compact answer and cites source labels once

#### Scenario: No validated claim available
- **WHEN** no validated claim covers the question
- **THEN** the deterministic composer returns an insufficiency, ambiguity, conflict, permission, or runtime-unavailable response according to the answer packet status
