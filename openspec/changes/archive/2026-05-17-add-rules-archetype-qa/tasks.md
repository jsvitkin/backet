## 1. QA Case Schema

- [x] 1.1 Inspect the current rules answer QA case loader, fixture format, and report format.
- [x] 1.2 Extend the case schema with archetype, difficulty, evidence contract ID, required facets, accepted source roles, forbidden source roles, answerability expectation, variant metadata, and failure expectations.
- [x] 1.3 Add validation errors that identify invalid archetype QA fields by path before running bot queries.
- [x] 1.4 Keep fixtures portable and non-copyright-infringing by using source labels, page anchors, facets, and bounded snippets only where needed.

## 2. Archetype Case Set

- [x] 2.1 Add baseline cases for definition, procedure, cost, resource quantity, targeting, restriction, interaction, base-vs-specific, cross-reference, conflict, and insufficiency archetypes.
- [x] 2.2 Cover very easy, easy, medium, hard, and very hard difficulty levels with realistic session-style player phrasing.
- [x] 2.3 Add deterministic prompt variants that preserve the expected evidence contract while changing wording, synonyms, and table framing.
- [x] 2.4 Include cases that catch flavor/example evidence used as rules, specific-only evidence used as base rules, missing target constraints, and confident answers from partial evidence.

## 3. Evaluator And Failure Classification

- [x] 3.1 Update the QA evaluator to grade scenario frame, contract selection, selected evidence, answerability, missing facets, and source roles before final answer text.
- [x] 3.2 Classify failures by earliest stage, missing facet, source-role misuse, answerability status, synthesis problem, citation problem, runtime problem, or output policy problem.
- [x] 3.3 Support archetype and difficulty filters for local smoke runs and focused debugging.
- [x] 3.4 Preserve existing fixed-prompt regression behavior for current QA cases.

## 4. Reports And Diagnostics

- [x] 4.1 Add human reports grouped by archetype, difficulty, evidence contract, answerability status, failure stage, and regression status.
- [x] 4.2 Add JSON reports with case result, variant metadata, contract expectations, diagnostics summary, selected source summaries, missing facets, and failure classifications.
- [x] 4.3 Add next-debug-command output for failed cases without printing raw JSON structures in human mode.
- [x] 4.4 Add regression coverage proving non-JSON QA output does not dump raw dictionaries, lists, machine payload keys, full source passages, source PDF paths, or secrets.

## 5. Tests And Documentation

- [x] 5.1 Add unit tests for archetype case loading, schema validation, variant expansion, and case filtering.
- [x] 5.2 Add evaluator tests for required facets, accepted/forbidden source roles, answerability expectations, and final answer text checks.
- [x] 5.3 Add integration tests that run a small archetype suite against deterministic fixture data.
- [x] 5.4 Update docs/wiki to explain archetype QA, how to read reports, and how to decide whether a failure belongs to ingestion, retrieval, answerability, synthesis, or runtime/model configuration.
- [x] 5.5 Run focused tests and OpenSpec validation for this change.
