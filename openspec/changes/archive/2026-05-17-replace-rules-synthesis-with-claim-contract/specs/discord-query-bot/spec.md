## ADDED Requirements

### Requirement: Final answers use supported claims
Discord rules answers SHALL be composed from validated supported claims and selected evidence only.

#### Scenario: Evidence contains direct claim
- **WHEN** selected evidence yields a validated claim that answers the user's question
- **THEN** the bot sends a compact direct answer with source labels for the supporting evidence

#### Scenario: Evidence lacks direct claim
- **WHEN** selected evidence or fallback context does not yield a validated claim
- **THEN** the bot says the permitted sources are insufficient rather than formatting a related snippet as an answer

#### Scenario: Claim support conflicts
- **WHEN** comparable selected sources support conflicting claims
- **THEN** the bot reports conflict or ambiguity instead of selecting whichever claim ranks first

### Requirement: Local model assistance is bounded
Optional local model synthesis SHALL be limited to bounded extraction, ranking, judging, or prose repair tasks over selected evidence and validated claims.

#### Scenario: Model proposes claim
- **WHEN** a local model proposes a claim from selected evidence
- **THEN** deterministic validation must confirm the claim support before the claim can be used in final output

#### Scenario: Model writes unsupported prose
- **WHEN** local model prose omits required citations, adds unsupported claims, or fails to cover validated claims
- **THEN** validation rejects the prose and the configured fallback or abstain policy is applied

#### Scenario: Quality profile requires model
- **WHEN** a runtime profile requires model-assisted judging and the model service is unavailable
- **THEN** the bot returns runtime-unavailable instead of silently downgrading to unjudged prose
