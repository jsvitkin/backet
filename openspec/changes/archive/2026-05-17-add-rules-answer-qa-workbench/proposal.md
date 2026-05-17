## Why

The rules bot can now expose traces, but the quality checks are not connected to realistic Discord questions. We need a repeatable QA workbench that proves whether retrieval, answerability, and synthesis improved before we ship another bot release.

## What Changes

- Add a rules answer QA workbench for running curated player-style questions against a vault or exported bot bundle.
- Add a durable QA case format with difficulty, expected answer stance, required source anchors, forbidden answer patterns, and stage-level expectations.
- Add concise human reports and deterministic JSON output that identify whether a failure is planner, retrieval, answerability, synthesis, or runtime configuration.
- Add regression fixtures based on the Prague failures: Obfuscate learning, Dementation targeting, Blood Bonds, ritual timing, and messy critical consequences.
- Add a CI/local quality gate that can fail when known QA cases regress.
- Do not store source PDFs or full rulebook text in repo fixtures; fixtures store questions, expected citations or anchors, and small answer expectations only.

## Capabilities

### New Capabilities
- `rules-answer-qa-workbench`: Runs realistic bot-answer QA cases and classifies failures by pipeline stage.

### Modified Capabilities
- `answer-quality-diagnostics`: Adds a runtime-facing diagnostics contract consumed by the QA workbench.
- `discord-query-bot`: Adds QA execution entry points for bot playground and bundle answers.
- `quality-gates`: Adds answer-quality regression gates for local validation and release readiness.

## Impact

- Affected CLI: new or extended `backet bot qa` / playground QA command surface, JSON payloads, and human reports.
- Affected tests: regression fixtures and integration tests that run against synthetic vaults, plus optional Prague-local smoke cases when that vault is present.
- Affected per-vault state: QA reports may be written under `.backet/reports/answer-quality/` when requested; they are rebuildable and may be ignored or committed at the Storyteller's discretion.
- Affected repo assets: no copyrighted source PDFs or long source excerpts are stored.
- Skills are not changed in this slice; they can later reference the QA command when preparing bot releases.

