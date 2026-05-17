## Why

The latest local sandbox run showed that the bot can pass the narrow screenshot-derived cases while regressing on ordinary table questions. We need a broader, repeatable QA suite that measures planner, retrieval, answerability, synthesis, and citation quality separately before we keep changing the pipeline.

## What Changes

- Expand the rules answer QA workbench with a broad standard case suite built from normal player-session questions across difficulty bands and rules categories.
- Add case fields for direct-answer expectations, stance, answerability, selected evidence anchors, forbidden evidence, and expected failure stage.
- Separate CI-required cases, local exploratory cases, and private-vault calibration cases so the suite is useful without making every local vault dependency a release blocker.
- Improve reports so failed cases identify whether the first failure is planner, retrieval, answerability, claim support, synthesis, citation, runtime, or output policy.
- Keep generated reports in derived paths such as `.backet/reports/answer-quality/`; no canonical vault notes or source PDFs are modified.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `rules-answer-qa-workbench`: broaden case schema, case suites, difficulty/category coverage, and stage-aware reporting.
- `answer-quality-diagnostics`: expose normalized trace fields needed by the expanded QA evaluator.
- `quality-gates`: distinguish required standard QA gates from local/private exploratory suites.

## Impact

- Affected code: answer QA case loader/evaluator, local bot QA command, answer trace normalization, fixture corpus setup, JSON and human reports.
- Affected data: versioned QA case files under repository resources, optional derived reports under a caller-selected path or vault-local `.backet/reports/answer-quality/`.
- Affected systems: local validation and CI quality gates. Private vault calibration remains local and skipped when the configured vault is unavailable.
- Non-goals: this change does not alter retrieval, corpus ingestion, or answer synthesis behavior; it creates the measurement harness needed to implement those safely.
