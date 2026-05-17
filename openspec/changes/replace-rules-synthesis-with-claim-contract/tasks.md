## 1. Claim Contract

- [ ] 1.1 Define the supported claim data model with text, source IDs, support spans/windows, covered entities, covered intent, stance, constraints, confidence, and validation status.
- [ ] 1.2 Add claim extraction diagnostics to answer traces without exposing unbounded source text or prompts.
- [ ] 1.3 Add tests for claim schema serialization and paste-safe diagnostics.

## 2. Deterministic Extraction And Composition

- [ ] 2.1 Implement deterministic claim extraction from selected evidence and the resolved query plan.
- [ ] 2.2 Implement claim validation against selected evidence, source IDs, support spans, stance, intent, and target constraints.
- [ ] 2.3 Replace deterministic fallback sentence picking with claim-based final answer composition.
- [ ] 2.4 Ensure fallback context and rejected candidates cannot support substantive claims.

## 3. Model-Assisted Roles

- [ ] 3.1 Update model prompts so local models propose or repair claims/prose over selected evidence and validated claim outlines.
- [ ] 3.2 Validate all model-proposed claims deterministically before final output.
- [ ] 3.3 Enforce runtime profile behavior for unavailable required model assistance and degraded optional fallback.
- [ ] 3.4 Record model validation errors and final fallback decisions in diagnostics.

## 4. QA And Verification

- [ ] 4.1 Extend QA evaluator support for required claim patterns, stance, final answer support mapping, and unsupported-text failures.
- [ ] 4.2 Add regression cases for Rouse Check definition, bagged blood, Blush of Life, Hunger 5 failed Rouse Check, and Dominate eye contact.
- [ ] 4.3 Run fixture-backed required QA and local Prague calibration with `--use-model`, recording model fallback frequency and final correctness.
- [ ] 4.4 Run the full test suite and `openspec validate --all --strict`.
