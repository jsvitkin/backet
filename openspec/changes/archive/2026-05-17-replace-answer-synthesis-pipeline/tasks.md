## 1. Answer Packet Contract

- [x] 1.1 Define answer packet data structures for question, evidence status, selected evidence, missing evidence, ambiguity, and answer shape
- [x] 1.2 Add compatibility mapping from current source lists to answer packets
- [x] 1.3 Include answer packet summaries in local diagnostics

## 2. Evidence-Aware Template Mode

- [x] 2.1 Refactor template generation to consume answer packets
- [x] 2.2 Add answerable, insufficient, ambiguous, conflicting, and runtime-unavailable response classes
- [x] 2.3 Remove reliance on raw sentence overlap as the primary answer decision
- [x] 2.4 Preserve concise source detail formatting and `/bot sources` compatibility

## 3. Model Synthesis

- [x] 3.1 Update local model prompt construction to consume answer packets
- [x] 3.2 Add validation for citation presence, unavailable citations, response limits, and evidence-status violations
- [x] 3.3 Ensure model fallback returns evidence-aware template output
- [x] 3.4 Add tests proving insufficient evidence cannot become a substantive model answer

## 4. Discord Integration

- [x] 4.1 Wire evidence-aware answer synthesis into bot runtime
- [x] 4.2 Preserve authorization and response visibility behavior
- [x] 4.3 Verify message splitting and mention sanitization with evidence-aware answers

## 5. Validation

- [x] 5.1 Add unit tests for all response classes
- [x] 5.2 Add integration tests for template and model fallback behavior
- [x] 5.3 Run answer-quality regression cases and full test suite
- [x] 5.4 Run OpenSpec validation
