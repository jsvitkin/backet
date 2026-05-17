## 1. Case Schema And Suites

- [x] 1.1 Extend the QA case schema with suite name, category, severity, expected first failure stage, direct answer expectations, and claim-support fields.
- [x] 1.2 Split existing screenshot-derived cases into a named regression group without removing their current coverage.
- [x] 1.3 Add a fixture-backed standard suite covering very easy, easy, medium, hard, and very hard player-session questions.
- [x] 1.4 Add negative cases for insufficiency, ambiguity, and conflict behavior.

## 2. Evaluator And Reports

- [x] 2.1 Update the evaluator to classify planner, retrieval, answerability, synthesis, citation, runtime, and output-policy failures independently.
- [x] 2.2 Add suite severity handling so required failures exit non-zero and exploratory failures can report without failing by default.
- [x] 2.3 Add ad hoc fresh-question report support with JSON and Markdown outputs.
- [x] 2.4 Ensure human output stays concise and JSON output carries complete deterministic diagnostics.

## 3. Integration

- [x] 3.1 Add fixture corpus or bundle setup for required QA cases without relying on private vaults or source PDFs.
- [x] 3.2 Wire required QA into the local validation command or documented test target.
- [x] 3.3 Keep private-vault calibration skipped when local paths or model services are unavailable.
- [x] 3.4 Update documentation for required, exploratory, and private-vault QA modes.

## 4. Verification

- [x] 4.1 Add unit tests for case schema validation and invalid field errors.
- [x] 4.2 Add integration tests proving stage classification on planner, retrieval, answerability, synthesis, and model-fallback failures.
- [x] 4.3 Run the required answer QA suite and record pass/fail totals in the change notes.
- [x] 4.4 Run `openspec validate --all --strict`.

## Validation Notes

- `pytest tests/test_answer_quality.py tests/test_bot_qa.py tests/test_workflow_assets.py::test_private_discord_bot_docs_cover_setup_and_troubleshooting -q`: 18 passed.
- `backet bot qa E:\Projects\prague-by-night --suite screenshot-regression --role-id 1117554581904294018 --limit 8 --report-output E:\Projects\prague-by-night\.backet\qa\required-suite-after-expanded-qa`: 4/5 passed; the Dementation case fails at retrieval and remains evidence for the next retrieval-focused changes.
