## Context

Today, the template answer generator chooses sources, extracts segments that overlap query terms, and formats them as a short answer plus source detail. The local Llama path receives selected snippets and is validated mainly for citation presence and length. Both modes are downstream of retrieval quality, but neither has a robust concept of evidence sufficiency.

After query planning and RAG v2 retrieval, answer generation should consume an evidence packet:

```text
evidence packet
  -> answer policy
  -> deterministic answer or model prompt
  -> grounding validation
  -> Discord-safe response
```

This keeps generation honest: answerable questions get concise answers; insufficient or ambiguous evidence gets an honest refusal or clarification.

## Goals / Non-Goals

**Goals:**
- Make evidence status control answer behavior.
- Generate direct, compact, Discord-friendly answers from vetted evidence.
- Refuse when sources are insufficient instead of turning nearby mentions into answers.
- Preserve citations and source details.
- Keep local model synthesis optional, bounded, and validated.
- Make template fallback safe and useful.

**Non-Goals:**
- Do not introduce new retrieval ranking in this change.
- Do not require a larger model or paid host.
- Do not generate uncited advice from general model knowledge.
- Do not answer hidden Storyteller content for player commands.
- Do not expose raw prompts, secrets, or unbounded source text in Discord.

## Decisions

### Decision: Introduce an answer packet consumed by formatters

Answer synthesis should work from an answer packet containing:

- original question and query plan summary
- evidence status
- selected evidence snippets and citations
- missing evidence or ambiguity details
- desired answer shape
- safety and visibility policy

Rationale: generation should not need to inspect raw retrieval internals. It should know whether evidence is sufficient and how to respond.

Alternative considered: let the model inspect all candidate diagnostics. That increases prompt size and invites the model to reinterpret rejected evidence.

### Decision: Evidence status drives response class

The answer pipeline should have explicit response classes:

- `answer`: evidence supports a direct response
- `insufficient`: retrieved sources do not answer the question
- `ambiguous`: multiple comparable sources require narrowing or Storyteller choice
- `conflicting`: sources appear to disagree
- `permission-denied`: existing authorization behavior
- `runtime-unavailable`: retrieval or model dependency unavailable

Rationale: "I found text" is not the same thing as "I can answer." The observed failures are mostly missing this distinction.

### Decision: Template fallback becomes evidence-aware

Template mode should not simply pick overlapping sentences. It should format:

- a short answer when evidence status is `answer`
- a concise insufficiency message when status is `insufficient`
- a narrowing prompt when status is `ambiguous` or `conflicting`

Rationale: fallback should be less eloquent but still correct. It should not be the dumb path.

Alternative considered: remove template mode. That would make hosting and availability harder, especially on low-resource deployments.

### Decision: Model synthesis is a bounded paraphraser, not an independent rules expert

When model mode is enabled, the prompt should include only the answer packet evidence and task-specific shape instructions. The model must not use general knowledge, hidden context, or rejected candidates. Validation should check:

- required citations or source labels
- maximum length
- no unsupported source labels
- no obvious unsupported claims when rule terms are absent from evidence
- refusal preserved when evidence status is insufficient

Rationale: a smarter model can improve prose, but it must not compensate for missing evidence by inventing.

### Decision: Discord formatting remains compact

Discord output should keep:

- direct answer first
- concise bullets when procedural
- source detail after the answer
- source summary available through `/bot sources`
- split messages only when needed

Rationale: the bot is used in play. The output should be useful at the table, not a research dump.

## Risks / Trade-offs

- More refusals may feel worse before retrieval improves -> diagnostics should identify missing evidence so later changes can target retrieval gaps.
- Validation of unsupported claims is hard -> start with conservative structural validation and source-term checks, then add stronger grounding checks later.
- Template answers may become less detailed -> prefer correct and concise over wrong and verbose.
- Ambiguity messages may interrupt play -> keep them short and ask for a narrowing term such as book, clan, discipline, or scope.

## Migration Plan

1. Add answer packet support while preserving current answer generator interfaces.
2. Teach template mode to honor evidence status.
3. Update local model prompt building to consume answer packets.
4. Add grounding validation and fallback behavior.
5. Switch Discord bot runtime to answer packets when RAG v2 evidence is available, with compatibility fallback for current sources.

Rollback can use the existing template generator for direct source lists, but diagnostics should make that fallback visible.

## Open Questions

- None requiring user input. The architecture decision is to keep model generation optional and evidence-bound, not to make a model the source of truth.
