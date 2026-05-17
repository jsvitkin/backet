## Context

The current QA loop is useful for proving that specific reported bugs do not recur, but it is too easy to overfit fixes to named questions. The failures we care about are broader: confusing flavor with rules, answering a base-rule question from a specific power, missing target restrictions, treating missing evidence as permission, or producing a confident answer when the packet is partial.

This change adds archetype-based QA on top of the answer-quality workbench. It measures the rules pipeline by question shape, evidence contract, difficulty, and failure stage. It uses local vault indexes and local model/runtime configuration during execution, but the repo stores only portable, non-copyright-infringing case metadata and expected facets.

## Goals / Non-Goals

**Goals:**
- Define a taxonomy for player-facing rules-question archetypes and difficulties.
- Express expected behavior as evidence facets, source constraints, answer class, and forbidden failure patterns.
- Run fresh prompt variants so QA measures generalization instead of memorization.
- Report failures by archetype, contract, stage, source quality, and regression status.
- Make QA output useful for deciding whether the next fix belongs in ingestion, retrieval, answerability, synthesis, or model/runtime configuration.

**Non-Goals:**
- Do not replace implementation-level unit tests.
- Do not require committing proprietary rulebook passages to the repository.
- Do not alter production bot behavior directly.
- Do not require remote model services.

## Decisions

1. Store archetype cases as portable fixtures.

   QA fixtures should include question text or generated variants, difficulty, archetype, expected answer class, required evidence facets, accepted source anchors, forbidden source roles, and output checks. They should not contain long copyrighted source passages.

   Alternative considered: store full expected answers. That makes tests fragile and encourages wording over correctness.

2. Evaluate evidence contracts before final text patterns.

   The workbench should first inspect diagnostics for scenario frame, contract, selected evidence, missing facets, and answerability. Only after those pass should it apply final answer text checks. This keeps retrieval and synthesis failures distinct.

   Alternative considered: use text-only grading. That can catch bad visible answers, but it cannot tell why the answer failed.

3. Add prompt variants per archetype.

   Each archetype should include stable baseline cases plus variants that change phrasing, table framing, and synonyms while preserving the same evidence contract. The generated or curated variants must be deterministic enough for repeatable CI/local runs.

   Alternative considered: rely on the last failed sandbox questions. Those are valuable regressions, but they do not prove broader improvement.

4. Keep reports concise for humans and complete for agents.

   Human output should summarize pass/fail by archetype and stage, list the worst failures, and show the next debug command. JSON should include each case, variant seed or ID, diagnostics, selected evidence summaries, failed facets, and final text checks.

5. Use the QA suite to tune thresholds across changes.

   The archetype suite is intended to accompany `derive-rules-rule-units` and `add-rules-scenario-answerability`. It should be able to run against chunk-only, rule-unit, and local-model profiles, making it useful during rollout and after model/provider changes.

## Risks / Trade-offs

- [Risk] Archetype cases may become too abstract. Mitigation: include realistic player phrasing and difficulty labels for each case.
- [Risk] Source anchors may differ between users' owned book editions. Mitigation: support evidence facets and source roles in addition to strict book/page anchors.
- [Risk] Model outputs vary. Mitigation: grade diagnostics and evidence contracts before text; keep final answer checks tolerant where wording is not material.
- [Risk] QA runtime may be slow with local models. Mitigation: support case filters, profiles, and concise smoke subsets.
- [Risk] Fixtures accidentally include too much source text. Mitigation: use labels, anchors, facets, and short non-substantial snippets only when needed.

## Migration Plan

1. Extend QA case schema with archetype, difficulty, evidence facets, contract ID, variant metadata, source role constraints, and failure expectations.
2. Add a starter archetype case set that covers simple through very hard player questions without reusing the latest failed prompts as the whole suite.
3. Update the workbench evaluator to read scenario/answerability diagnostics and classify failures by stage and facet.
4. Add human and JSON reports grouped by archetype, difficulty, contract, and failure stage.
5. Add CI/local smoke commands and documentation for running against fixture corpora and local vault indexes.

## Open Questions

None for the proposal. Case contents and thresholds should be adjusted through implementation review and QA results, not by adding one-off fixes for individual prompts.
