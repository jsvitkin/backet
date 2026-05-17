## Why

The bot still fails medium and hard table questions because it retrieves plausible mentions instead of proving that the evidence packet answers the player's scenario. We need query-time scenario framing and explicit evidence contracts so the system can assemble the right base rules, specific rules, exceptions, and missing-facet diagnostics before synthesis.

## What Changes

- Add a scenario frame step to the rules query planner that extracts the player's requested action, actor, target, mechanic or entity, conditions, polarity, and requested answer shape.
- Introduce evidence contracts for common rules-question shapes, including definition, procedure, cost, resource quantity, targeting, restriction, interaction, exception, and insufficiency questions.
- Require retrieval to build a connected evidence packet that satisfies the selected contract before the answer synthesis stage can produce a confident answer.
- Prefer rule-unit evidence when available, while preserving chunk fallback and exact-search fallback for unstructured or not-yet-derived areas of the corpus.
- Add answerability decisions that distinguish enough evidence, partial evidence, conflicting evidence, and insufficient evidence with machine-readable missing facets.
- Update diagnostics so QA can identify whether a failure happened in scenario framing, evidence assembly, retrieval coverage, or synthesis.
- Keep retrieval bounded to selected rule units, linked source chunks, and targeted neighbor windows; this change must not imply loading whole rulebooks into model context.
- Non-goal: this change does not hardcode answers to previously failed questions and does not choose a new hosted model provider.

## Capabilities

### New Capabilities
- `rules-scenario-answerability`: Defines scenario frames, evidence contracts, connected evidence packets, answerability decisions, and missing-facet reporting for rules questions.

### Modified Capabilities
- `rules-query`: The query planner must classify rules questions into scenario frames and evidence contracts before retrieval and synthesis.
- `hybrid-rules-retrieval`: Retrieval must assemble contract-aware evidence packets from rule units, chunks, exact matches, and targeted neighbor expansion.
- `answer-quality-diagnostics`: Diagnostics must expose scenario-frame, evidence-contract, answerability, and missing-facet data for each answer attempt.

## Impact

- CLI: extends rules query planning, retrieval packet assembly, answerability evaluation, and debug output.
- Per-vault state: may read rule units and existing indexes from `.backet/`; it should not require committing machine-specific runtime traces.
- Ingested rules corpus: uses derived rule units when present and remains compatible with raw chunk evidence.
- Discord bot: benefits through the existing rules-query pipeline; bot command UX should remain stable unless diagnostics are explicitly requested.
- Skills: may reference the new diagnostics, but skills should continue delegating retrieval and answerability to the CLI.
- Dependencies: can use the configured local model for scenario interpretation when appropriate, with deterministic fallbacks and visible diagnostics.
