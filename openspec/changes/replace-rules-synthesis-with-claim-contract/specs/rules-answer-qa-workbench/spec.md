## ADDED Requirements

### Requirement: Claim-level QA assertions
The rules answer QA workbench SHALL evaluate whether final answers are supported by validated claims.

#### Scenario: Required claim missing
- **WHEN** a QA case defines a required claim pattern or stance and synthesis does not produce a validated matching claim
- **THEN** the case fails at claim-support or synthesis stage

#### Scenario: Unsupported final text
- **WHEN** final answer text includes a substantive statement not mapped to a validated claim
- **THEN** the case fails at synthesis stage

#### Scenario: Correct abstain
- **WHEN** a QA case expects insufficient evidence and no validated claim is produced
- **THEN** the case passes if the final answer abstains and does not include unsupported substantive rules advice
