## Why

The current fallback composer can retrieve correct evidence and still answer with the wrong sentence. Model synthesis also fails too often on citation/outline validation, so the visible answer must be built from validated claims rather than from raw source snippets or untrusted prose.

## What Changes

- Introduce a rules answer claim contract between evidence retrieval and final Discord text.
- Extract answer claims with source IDs, covered intent, stance, target constraints, support spans, and confidence before composing final prose.
- Validate that at least one claim directly answers the planned question before producing a substantive answer.
- Use optional local models for bounded extraction, ranking, or judging jobs while keeping deterministic validation and final support checks authoritative.
- Replace deterministic fallback sentence picking with a claim-based composer that cites only supported selected evidence.

## Capabilities

### New Capabilities

- `rules-answer-claim-contract`: intermediate supported-claim representation used by deterministic and model-assisted answer synthesis.

### Modified Capabilities

- `discord-query-bot`: final answers are composed only from validated claims and abstain when no direct claim covers the question.
- `answer-quality-diagnostics`: expose claim extraction, support spans, validation, model judge decisions, and final composer mode.
- `rules-answer-qa-workbench`: evaluate claim support and distinguish claim extraction failures from retrieval failures.

## Impact

- Affected code: bot answer packet handling, deterministic composer, model prompt/validation, fallback policy, diagnostics, QA evaluator, Discord formatting tests.
- Affected data: no canonical vault notes or source PDFs are modified. Optional QA reports may include bounded claim/support diagnostics.
- Dependencies: should be applied after `add-rules-entity-first-retrieval` so claim extraction receives stricter selected evidence.
- Non-goals: this change does not add a remote model dependency or trust local model output without deterministic validation.
