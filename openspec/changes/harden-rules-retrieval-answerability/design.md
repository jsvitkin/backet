## Context

Current exact retrieval builds an FTS query by joining all terms with OR. That gives high recall but weak precision: a query about Dementation targeting can retrieve any chunk containing Malkavian or victim. Current evidence cues are also broad; words such as "victim", "vampire", or "kindred" can satisfy targeting evidence even when the chunk does not answer the user's targeting question.

This change makes the pipeline honest. It should prefer saying "I found related material but not enough evidence" over quoting a plausible but wrong passage.

## Goals / Non-Goals

**Goals:**
- Keep all high-value user terms unless they are explicitly normalized to an accepted alias.
- Require entity and intent evidence to co-occur for answerable mechanical questions.
- Separate selected evidence from fallback context.
- Make degraded semantic retrieval visible and quality-gated.
- Preserve bounded retrieval and avoid loading whole rulebooks.

**Non-Goals:**
- Do not introduce a full mechanics database.
- Do not solve answer prose quality; that belongs to `replace-rules-answer-synthesis`.
- Do not require reingesting source PDFs unless index repair later proves stored chunks are structurally unusable.

## Decisions

1. Use anchored retrieval plans.
   - A planned query will have an entity anchor group, an intent/evidence group, and optional raw terms.
   - Exact channels should try anchored AND/NEAR-style retrieval first, then phrase/alias/metadata, then broad fallback.
   - Broad fallback never marks evidence answerable by itself.

2. Treat answerability as a contract, not a confidence label.
   - A selected evidence packet must show the requested entity or accepted alias, the requested intent cue, and a source section that is mechanically appropriate.
   - If these conditions are missing, the packet is insufficient and the bot should abstain or ask for narrowing.

3. Grade semantic quality.
   - `hash` embeddings remain allowed in lite mode for cheap local behavior.
   - Standard and quality profiles must report degraded/unavailable semantic services as a runtime quality problem.

4. Make rejection visible.
   - Rejected candidates should include reasons such as `missing_entity_anchor`, `missing_intent_evidence`, `mere_mention`, `degraded_semantic_only`, or `low_quality_section`.

## Risks / Trade-offs

- Stricter retrieval may answer fewer questions at first. Mitigation: QA reports will separate true corpus gaps from retriever bugs.
- SQLite FTS NEAR behavior may be limited. Mitigation: implement anchored scoring and post-filtering even when FTS cannot express every constraint.
- Some answerable rules are split across nearby chunks. Mitigation: allow bounded neighboring chunk expansion once an anchor chunk is found.
- Hash embeddings may still look useful in traces. Mitigation: semantic quality becomes explicit and cannot satisfy non-lite runtime profiles alone.

## Migration Plan

Existing rules databases continue to load. Users should run `backet rules index <vault> --full` after implementation so retrieval metadata reflects the stricter schema. Reingestion is only required if `repair-rules-corpus-indexing` reports that stored chunks lack usable source text or structure.

