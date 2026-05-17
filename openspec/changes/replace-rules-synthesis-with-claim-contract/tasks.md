## 1. Claim Contract

- [x] 1.1 Define the supported claim data model with text, source IDs, support spans/windows, covered entities, covered intent, stance, constraints, confidence, and validation status.
- [x] 1.2 Add claim extraction diagnostics to answer traces without exposing unbounded source text or prompts.
- [x] 1.3 Add tests for claim schema serialization and paste-safe diagnostics.

## 2. Deterministic Extraction And Composition

- [x] 2.1 Implement deterministic claim extraction from selected evidence and the resolved query plan.
- [x] 2.2 Implement claim validation against selected evidence, source IDs, support spans, stance, intent, and target constraints.
- [x] 2.3 Replace deterministic fallback sentence picking with claim-based final answer composition.
- [x] 2.4 Ensure fallback context and rejected candidates cannot support substantive claims.

## 3. Model-Assisted Roles

- [x] 3.1 Update model prompts so local models propose or repair claims/prose over selected evidence and validated claim outlines.
- [x] 3.2 Validate all model-proposed claims deterministically before final output.
- [x] 3.3 Enforce runtime profile behavior for unavailable required model assistance and degraded optional fallback.
- [x] 3.4 Record model validation errors and final fallback decisions in diagnostics.

## 4. QA And Verification

- [x] 4.1 Extend QA evaluator support for required claim patterns, stance, final answer support mapping, and unsupported-text failures.
- [x] 4.2 Add regression cases for Rouse Check definition, bagged blood, Blush of Life, Hunger 5 failed Rouse Check, and Dominate eye contact.
- [x] 4.3 Run fixture-backed required QA and local Prague calibration with `--use-model`, recording model fallback frequency and final correctness.
- [x] 4.4 Run the full test suite and `openspec validate --all --strict`.

Validation notes:

- Added claim contract serialization and selected-evidence-only support tests in `tests/test_bot_answers.py`.
- Ran the full test suite with `pytest -q` successfully.
- Ran Prague screenshot-regression QA in template mode: 4/5 passed, with `malkavian-dementation-targeting` still failing at retrieval.
- Ran Prague `standard-fresh` QA with `--use-model --no-fail-on-failure`: 1/5 passed. The local model path remains exploratory; several failures are synthesis/direct-answer issues and Dominate eye-contact is still retrieval-sensitive.
- `openspec validate replace-rules-synthesis-with-claim-contract --strict` passed.
