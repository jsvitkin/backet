## 1. Answer Packet Contract

- [ ] 1.1 Define answer packet data structures for question, evidence status, selected evidence, missing evidence, ambiguity, and answer shape
- [ ] 1.2 Add compatibility mapping from current source lists to answer packets
- [ ] 1.3 Include answer packet summaries in local diagnostics

## 2. Evidence-Aware Template Mode

- [ ] 2.1 Refactor template generation to consume answer packets
- [ ] 2.2 Add answerable, insufficient, ambiguous, conflicting, and runtime-unavailable response classes
- [ ] 2.3 Remove reliance on raw sentence overlap as the primary answer decision
- [ ] 2.4 Preserve concise source detail formatting and `/bot sources` compatibility

## 3. Model Synthesis

- [ ] 3.1 Update local model prompt construction to consume answer packets
- [ ] 3.2 Add validation for citation presence, unavailable citations, response limits, and evidence-status violations
- [ ] 3.3 Ensure model fallback returns evidence-aware template output
- [ ] 3.4 Add tests proving insufficient evidence cannot become a substantive model answer

## 4. Discord Integration

- [ ] 4.1 Wire evidence-aware answer synthesis into bot runtime
- [ ] 4.2 Preserve authorization and response visibility behavior
- [ ] 4.3 Verify message splitting and mention sanitization with evidence-aware answers

## 5. Validation

- [ ] 5.1 Add unit tests for all response classes
- [ ] 5.2 Add integration tests for template and model fallback behavior
- [ ] 5.3 Run answer-quality regression cases and full test suite
- [ ] 5.4 Run OpenSpec validation
