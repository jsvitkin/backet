## 1. Case Schema and Evaluator

- [x] 1.1 Define the QA case schema with difficulty, command route, expected answer class, planner expectations, source anchors, answer patterns, and forbidden patterns.
- [x] 1.2 Extend `answer_quality.py` to evaluate stage-level expectations from bot answer traces.
- [x] 1.3 Add unit tests for valid cases, invalid cases, planner failures, retrieval failures, synthesis failures, and skipped private-vault cases.

## 2. CLI Workbench

- [x] 2.1 Add a local QA command that can run against a vault path or exported bundle.
- [x] 2.2 Reuse bot playground export/runtime paths so QA exercises production answer behavior.
- [x] 2.3 Add concise human output with pass/fail totals, failed stages, and next diagnostic action.
- [x] 2.4 Add deterministic JSON output with complete case results and bounded trace summaries.

## 3. Regression Suites

- [x] 3.1 Create committed synthetic fixtures for simple and medium rules-answer cases.
- [x] 3.2 Add a private-vault-friendly Prague case pack template covering Obfuscate learning, Dementation targeting, Blood Bonds, ritual timing, and messy critical consequences.
- [x] 3.3 Add tests proving fixture files do not include long copyrighted source excerpts.

## 4. Quality Gates

- [x] 4.1 Wire the standard QA suite into the test suite or a documented release-validation command.
- [x] 4.2 Ensure missing private vaults are reported as skipped and do not fail CI.
- [x] 4.3 Document how to run quick, standard, and full QA suites before deploying the Discord bot.
