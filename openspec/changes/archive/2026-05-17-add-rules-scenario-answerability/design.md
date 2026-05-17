## Context

The rules pipeline can now retrieve better source candidates than the original bot, but medium and hard questions still expose a deeper problem: retrieval often returns text that mentions the topic without proving the answer. Player questions are usually scenario-shaped: "Can this actor use this power on that target under these conditions?", "How do I do this at the table?", or "What cost or roll applies here?"

This change inserts a scenario framing and evidence-contract stage between natural language query planning and answer synthesis. It consumes existing chunks, planned retrieval channels, and the rule-unit layer from `derive-rules-rule-units` when available. It does not load whole rulebooks; it builds bounded evidence packets from selected rule units, linked source chunks, exact matches, semantic matches, and targeted neighbor windows.

## Goals / Non-Goals

**Goals:**
- Convert natural-language rules questions into scenario frames with actor, action, target, mechanic, conditions, polarity, and requested answer shape.
- Select an evidence contract that defines which facets are required before an answer can be confident.
- Assemble connected evidence packets that combine base rules, specific rules, exceptions, and source references.
- Report answerability as enough, partial, conflicting, or insufficient with machine-readable missing facets.
- Expose diagnostics that show whether a failure came from scenario framing, retrieval, evidence assembly, or synthesis.

**Non-Goals:**
- Do not hardcode answers for the failed QA questions.
- Do not require a new hosted model provider.
- Do not remove deterministic fallback answers.
- Do not replace rule-unit derivation; consume it opportunistically and fall back to chunks when needed.

## Decisions

1. Use scenario frames as typed query-plan extensions.

   The query planner already normalizes aliases and classifies intent. This change extends that output with scenario fields rather than introducing a separate command path. The frame should preserve raw text, normalized terms, ambiguity warnings, and confidence so diagnostics can explain what the system understood.

   Alternative considered: let the synthesis model infer the scenario directly from retrieved context. That hides mistakes until final text and makes retrieval unable to search for missing facets.

2. Use evidence contracts as answerability rules.

   Each archetype declares required evidence facets, acceptable source roles, and missing-facet behavior. For example, a targeting question needs the mechanic, target, system text or restriction, and relevant exception evidence. A resource quantity question needs the resource, quantity or cost, constraints, and source authority.

   Alternative considered: use one generic "enough evidence" score. A score cannot tell the difference between "found the power" and "found whether it works on another vampire."

3. Build connected evidence packets before synthesis.

   Retrieval should not simply pass top-k sources to the answer composer. It should assemble a packet that explains why each source is present: base rule, specific rule, exception, cross-reference, fallback, or rejected near miss. The packet is bounded by configured candidate and context limits.

   Alternative considered: increase top-k and rely on a stronger local model. That can help wording, but it also gives the model more unrelated text to confuse with the answer.

4. Prefer rule units, but retain chunk fallback.

   Rule units are the preferred evidence object because they carry mechanics roles and facets. However, not every corpus area will be perfectly derived. The contract evaluator must accept chunk evidence when it satisfies required facets and must mark gaps clearly when it does not.

   Alternative considered: require rule units for every answer. That would make early deployments too brittle and could regress simple questions.

5. Keep diagnostics paste-safe and QA-consumable.

   JSON traces should include scenario frame fields, contract ID, required facets, satisfied facets, missing facets, selected evidence IDs, rejected evidence summaries, and answerability status. Human output should summarize the status, selected sources, missing evidence, and next debug command without dumping full passages or raw structures.

## Risks / Trade-offs

- [Risk] Scenario framing can misclassify ambiguous user phrasing. Mitigation: preserve ambiguity warnings, use deterministic alias/entity cues, and allow insufficient/clarifying outcomes.
- [Risk] Evidence contracts may be too strict at first. Mitigation: distinguish partial from insufficient and include per-contract diagnostics to tune thresholds.
- [Risk] Local model interpretation may vary. Mitigation: keep contract schemas deterministic and log backend/model metadata when a model contributes.
- [Risk] Packet assembly increases latency. Mitigation: enforce candidate caps, cache rule-unit metadata, and keep neighbor expansion targeted.
- [Risk] Stronger abstention may feel worse before coverage improves. Mitigation: provide concise "I found X but still need Y" answers instead of silent failure.

## Migration Plan

1. Extend query-plan data structures with scenario-frame fields.
2. Add evidence-contract definitions and contract selection.
3. Build packet assembly over existing retrieval results and rule units when available.
4. Add answerability decisions and missing-facet diagnostics.
5. Update answer synthesis inputs to consume the evidence packet rather than raw top-k snippets.
6. Preserve current behavior behind fallback paths when scenario framing or contract assembly is unavailable.

## Open Questions

None for the proposal. The implementation should tune contract thresholds with the archetype QA suite rather than asking for manual per-question decisions.
