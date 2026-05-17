## Context

The bot currently returns source-grounded answers in the narrow sense that it formats retrieved snippets and citations. The failure mode is that retrieval can select irrelevant snippets, and the answer formatter then presents them as useful. The Discord screenshots show this clearly: a question about learning Obfuscate matched a phrase containing "learn" plus an unrelated Obfuscate listing, and a question about blood bonds matched unrelated "use" language.

The current runtime already records some diagnostics in memory and logs, but the diagnostics are not enough to run a repeatable quality loop. Operators need to know which stage failed:

```text
question
  -> retrieval candidates
  -> selected answer sources
  -> answerability decision
  -> final answer
```

This change creates the measuring stick for the later query planner, RAG v2 retriever, and synthesis changes.

## Goals / Non-Goals

**Goals:**
- Make answer failures reproducible from local commands without needing Discord screenshots.
- Emit deterministic diagnostics in JSON for agents and concise diagnostics in playground output for humans.
- Support regression cases that assert expected source books/pages, forbidden source patterns, and expected refusal when sources are insufficient.
- Preserve privacy boundaries: diagnostics expose bounded snippets and metadata, not whole books, whole vault sections, tokens, or source PDFs.
- Keep the capability useful with the current template answer engine while leaving room for future query-plan and answerability fields.

**Non-Goals:**
- Do not improve retrieval ranking in this change.
- Do not introduce a new model, reranker, embedding backend, or hosting profile.
- Do not change Discord response formatting for normal users.
- Do not store long-lived diagnostic traces in the vault by default.
- Do not require skills to parse bot internals; skills should call CLI diagnostics if needed.

## Decisions

### Decision: Add a structured answer trace object at the bot runtime boundary

The runtime should expose a structured trace in JSON flows. The trace should include:

- sanitized question preview and fingerprint
- command route and access tier
- vault and rules retrieval attempted flags
- retrieval errors
- candidate and selected source metadata already available to the runtime
- match reasons, scores, source labels, pages, section labels, and bounded snippets
- answer generation mode, fallback status, response size, and citation status
- placeholder fields for future `query_plan`, `evidence_gate`, and `reranker` diagnostics

Rationale: this keeps the diagnostic contract stable as deeper RAG stages are added.

Alternative considered: parse deployed Discord logs. Logs are useful operationally, but they are too lossy for regression testing and too awkward for local iteration.

### Decision: Store answer-quality cases as repo fixtures, not vault content

Regression questions should live in the repository test fixtures because they validate Backet behavior, not campaign canon. A case can define:

- command and question
- minimal fixture corpus or reference fixture bundle
- expected source predicates
- forbidden source predicates
- expected answer substrings or expected insufficiency/refusal
- notes explaining the real-world failure that motivated the case

Rationale: the cases should travel with code changes and run in CI. They are not canonical Obsidian notes and should not live in a user vault.

Alternative considered: storing cases in `.backet/`. That would help a single operator track their own bot quality, but it would not protect the product from regressions.

### Decision: Make evaluation stage-aware rather than a single pass/fail

Each case should report separate statuses for retrieval, answerability, and answer text. For example:

```text
retrieval: failed, wrong top source
answerability: failed, answer generated despite insufficient evidence
answer: failed, contains unrelated Second Inquisition text
```

Rationale: later changes will improve different stages. Stage-aware diagnostics prevent a final answer model from hiding retrieval failures by refusing every hard question.

Alternative considered: only asserting final output. That is simpler but too blunt for architecture work.

### Decision: Keep human output concise and JSON output complete

Human playground output should show the answer, top sources, scores, match reasons, and warnings. JSON output should carry the full diagnostic trace.

Rationale: humans need fast inspection; agents and tests need deterministic fields.

## Risks / Trade-offs

- Diagnostic output may expose too much private text -> enforce snippet limits and never include full source PDFs, full rule chunks beyond existing answer limits, tokens, role IDs beyond configured diagnostics, or raw model prompts unless explicitly requested in local debug mode.
- Fixtures may overfit the three screenshots -> include the screenshot cases as initial probes, but design the fixture format for broad future coverage.
- More JSON fields can become compatibility surface -> version the diagnostic schema or include a `trace_schema_version`.
- Diagnostics may be mistaken for quality improvements -> make proposals and tasks explicit that this change observes failures but does not fix retrieval.

## Migration Plan

1. Add trace fields behind existing JSON/playground commands.
2. Keep current output stable for normal Discord responses.
3. Add regression fixture support and seed it with the three observed failure families.
4. Run the new cases in CI as expected failures only if needed during the first commit, then tighten them as subsequent changes land.

Rollback is simple: the runtime can omit the new trace fields without affecting Discord command handling or bundle compatibility.

## Open Questions

- None requiring user input. The architecture call is to make diagnostics local, bounded, and stage-aware before changing retrieval.
