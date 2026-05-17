## Why

The current QA loop can prove that individual known prompts improved, but it does not reliably show whether the system became smarter across the kinds of questions players actually ask. We need archetype-based QA that tests evidence contracts and fresh prompt variants so we can tell feature iteration from regressions and avoid overfitting.

## What Changes

- Add a QA taxonomy for rules-question archetypes, including simple definition, procedure, cost, resource quantity, negative restriction, targeting, interaction, base-vs-specific, cross-reference, conflict, and legitimate insufficiency.
- Represent QA expectations as required evidence facets, acceptable answer classes, and source constraints rather than exact answer text only.
- Add variant prompts per archetype so the suite can test generalization without reusing only the questions that drove the change.
- Report results by archetype, difficulty, answerability decision, retrieval failure mode, synthesis failure mode, source quality, and regression status.
- Add checks that catch common bad behavior, including answering from flavor/example text, using a specific power as a base rule, ignoring target constraints, and fabricating an answer when required facets are missing.
- Keep QA assets as repo test data where they are portable and non-copyright-infringing; local vault state may provide runtime indexes but not proprietary source text in the repo.
- Non-goal: this change does not modify production answer behavior directly and does not replace implementation-level unit or integration tests.

## Capabilities

### New Capabilities
- `rules-archetype-qa`: Defines archetype-based rules QA cases, evidence-facet expectations, prompt variants, failure categorization, and reporting.

### Modified Capabilities
- `rules-answer-qa-workbench`: The QA workbench must run and report archetype/evidence-contract cases, not just fixed prompt regressions.
- `answer-quality-diagnostics`: Diagnostics must provide the failure categories and answerability fields required by archetype QA reports.

## Impact

- CLI: expands rules QA commands, reports, fixtures, and regression thresholds.
- Repo test data: adds portable archetype case definitions and non-proprietary expected metadata.
- Per-vault state: QA can run against local `.backet/` indexes, but generated traces and local model outputs remain machine-specific unless explicitly exported.
- Discord bot: no direct runtime behavior change; QA results guide later bot and retrieval iterations.
- Skills and wiki: documentation should explain how to interpret archetype QA results and when a failure points to retrieval, answerability, or synthesis.
