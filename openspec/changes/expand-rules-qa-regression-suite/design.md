## Context

The current answer QA suite mostly protects the specific failures seen in user screenshots. That helped prevent obvious repeats, but the fresh sandbox pass found failures on common session questions such as Rouse Checks, bagged blood, Blush of Life, Hunger 5, and Dominate eye contact. The next architecture changes need a wider measuring stick before and after implementation.

The CLI owns QA execution and report generation. Skills may reference the QA workflow, but they should not embed rules knowledge. Vault-local reports are derived artifacts under `.backet/`; source PDFs remain external and are not copied into the repo or vault.

## Goals / Non-Goals

**Goals:**

- Provide a standard, repository-owned QA suite that exercises realistic player questions across very easy, easy, medium, hard, and very hard cases.
- Classify the first failed pipeline stage so a bad final answer does not force manual archaeology through raw JSON.
- Support local private-vault calibration without requiring that vault in CI.
- Preserve concise human output and complete deterministic JSON output.

**Non-Goals:**

- Do not fix retrieval, ingestion, or synthesis in this change.
- Do not require source PDFs or private vault paths for CI-required cases.
- Do not store full rule text in reports beyond bounded snippets already allowed by diagnostics.

## Decisions

1. Add case suites instead of one flat case file.
   - Decision: use named suites such as `standard`, `pipeline-smoke`, `private-vault-calibration`, and `exploratory`.
   - Rationale: CI needs stable fixture-backed cases; local work needs Prague and model-backed checks.
   - Alternative considered: one monolithic case file. Rejected because private vault and model cases would either be skipped too often or make CI brittle.

2. Grade pipeline stages independently.
   - Decision: cases can assert planner terms, selected evidence anchors, answerability, claim/support fields, final answer patterns, citations, and runtime behavior.
   - Rationale: the observed failures often had the right evidence but the wrong visible answer, or weak evidence marked answerable.
   - Alternative considered: final-answer-only grading. Rejected because it hides where the pipeline failed.

3. Use required and exploratory severities.
   - Decision: required cases fail validation; exploratory cases report regressions without failing unless explicitly promoted.
   - Rationale: this allows broad coverage to exist before every pipeline piece is fixed.
   - Alternative considered: make every new case required immediately. Rejected because it would block incremental implementation of later changes.

4. Keep reports derived and paste-safe.
   - Decision: report artifacts include source labels, pages, stage diagnostics, hashes, and bounded snippets only.
   - Rationale: reports must be shareable without leaking PDFs, private vault text, or secrets.

## Risks / Trade-offs

- [Risk] The suite becomes a new form of overfitting. → Mitigation: require category and difficulty coverage, include negative/insufficient cases, and maintain exploratory fresh-question suites.
- [Risk] CI becomes slow if it exports bundles repeatedly. → Mitigation: use fixture corpora for required cases and allow bundle reuse for local/private suites.
- [Risk] Case expectations encode current bad architecture. → Mitigation: assert observable contracts and source anchors, not implementation-specific ranking internals unless diagnostics explicitly expose them.

## Migration Plan

1. Add the expanded case schema and standard fixture-backed cases.
2. Keep the existing screenshot-derived cases as a named legacy/regression group.
3. Add local Prague calibration cases as skipped-by-default unless the vault path is provided.
4. Promote cases from exploratory to required only when the relevant pipeline change is implemented.

## Open Questions

- None. Case suite names and required/exploratory behavior are architecture decisions for this change.
