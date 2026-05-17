## 1. Scenario Frame Model

- [ ] 1.1 Inspect the current rules query plan and answer trace structures.
- [ ] 1.2 Add scenario-frame fields for actor, action, target, mechanic/entity, conditions, polarity, requested answer shape, confidence, and ambiguity warnings.
- [ ] 1.3 Extend query planning to populate scenario frames for applicability, procedure, cost, quantity, restriction, interaction, exception, and definition questions.
- [ ] 1.4 Add deterministic fallback behavior for simple definition questions and unclear scenario-shaped questions.

## 2. Evidence Contracts

- [ ] 2.1 Define evidence-contract schemas for definition, procedure, cost, resource quantity, targeting, restriction, interaction, exception, conflict, and insufficiency.
- [ ] 2.2 Map query intents and scenario frames to evidence-contract IDs.
- [ ] 2.3 Define required facets, acceptable source roles, fallback source roles, and missing-facet behavior for each contract.
- [ ] 2.4 Add ambiguity handling when multiple mechanics, entities, or contracts are plausible.

## 3. Contract-Aware Retrieval Packets

- [ ] 3.1 Add evidence-packet data structures for selected evidence, evidence roles, satisfied facets, missing facets, rejected near misses, and source summaries.
- [ ] 3.2 Assemble evidence packets from rule units when available, with linked chunk context for auditability.
- [ ] 3.3 Assemble chunk-backed evidence packets when rule units are unavailable or incomplete.
- [ ] 3.4 Enforce configured candidate, unit, chunk, snippet, and neighbor-expansion bounds.
- [ ] 3.5 Add rejection reasons for high-scoring candidates that lack required contract facets or acceptable source roles.

## 4. Answerability And Synthesis Inputs

- [ ] 4.1 Implement answerability statuses for enough evidence, partial evidence, conflicting evidence, and insufficient evidence.
- [ ] 4.2 Prevent confident yes/no or procedural answers when required facets are missing.
- [ ] 4.3 Update synthesis inputs to consume evidence packets instead of unstructured top-k snippets where available.
- [ ] 4.4 Preserve deterministic fallback answers and existing command routes when scenario framing or packet assembly is unavailable.

## 5. Diagnostics And CLI UX

- [ ] 5.1 Extend JSON answer traces with scenario frame, contract ID, selected evidence IDs, satisfied facets, missing facets, answerability status, and rejection summaries.
- [ ] 5.2 Update human playground/query diagnostics to summarize selected sources, missing facets, and next debug command without dumping full passages.
- [ ] 5.3 Classify earliest failed stage among planning, scenario framing, contract selection, retrieval, evidence assembly, answerability, synthesis, citation, runtime, and output policy.
- [ ] 5.4 Add regression coverage proving non-JSON output does not dump raw dictionaries, lists, machine payload keys, full prompts, source PDF paths, or unbounded source text.

## 6. Tests And Documentation

- [ ] 6.1 Add unit tests for scenario framing, contract selection, ambiguity handling, and missing-facet behavior.
- [ ] 6.2 Add integration tests for targeting, procedure, resource quantity, negative restriction, interaction, conflict, and insufficiency questions.
- [ ] 6.3 Add tests proving high-scoring mentions are rejected when they do not satisfy the evidence contract.
- [ ] 6.4 Update docs/wiki for scenario answerability, diagnostics interpretation, and the bounded retrieval model.
- [ ] 6.5 Run focused tests, local sandbox smoke checks, and OpenSpec validation for this change.
