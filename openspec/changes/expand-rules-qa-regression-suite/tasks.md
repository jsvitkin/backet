## 1. Case Schema And Suites

- [ ] 1.1 Extend the QA case schema with suite name, category, severity, expected first failure stage, direct answer expectations, and claim-support fields.
- [ ] 1.2 Split existing screenshot-derived cases into a named regression group without removing their current coverage.
- [ ] 1.3 Add a fixture-backed standard suite covering very easy, easy, medium, hard, and very hard player-session questions.
- [ ] 1.4 Add negative cases for insufficiency, ambiguity, and conflict behavior.

## 2. Evaluator And Reports

- [ ] 2.1 Update the evaluator to classify planner, retrieval, answerability, synthesis, citation, runtime, and output-policy failures independently.
- [ ] 2.2 Add suite severity handling so required failures exit non-zero and exploratory failures can report without failing by default.
- [ ] 2.3 Add ad hoc fresh-question report support with JSON and Markdown outputs.
- [ ] 2.4 Ensure human output stays concise and JSON output carries complete deterministic diagnostics.

## 3. Integration

- [ ] 3.1 Add fixture corpus or bundle setup for required QA cases without relying on private vaults or source PDFs.
- [ ] 3.2 Wire required QA into the local validation command or documented test target.
- [ ] 3.3 Keep private-vault calibration skipped when local paths or model services are unavailable.
- [ ] 3.4 Update documentation for required, exploratory, and private-vault QA modes.

## 4. Verification

- [ ] 4.1 Add unit tests for case schema validation and invalid field errors.
- [ ] 4.2 Add integration tests proving stage classification on planner, retrieval, answerability, synthesis, and model-fallback failures.
- [ ] 4.3 Run the required answer QA suite and record pass/fail totals in the change notes.
- [ ] 4.4 Run `openspec validate --all --strict`.
