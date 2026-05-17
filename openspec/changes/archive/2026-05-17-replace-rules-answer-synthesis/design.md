## Context

The current template answerer works for very simple questions and for explicitly hard-coded cases such as ritual timing. It fails when the answer requires resolving user intent, combining evidence, or avoiding a tempting but irrelevant sentence. A stronger model alone would help only if it receives precise evidence and a clear answer contract.

This change creates that contract. Retrieval supplies an `AnswerPacket` with selected evidence, answer class, missing evidence, and source roles. Synthesis converts that packet into a bounded answer plan, then into Discord-ready prose.

## Goals / Non-Goals

**Goals:**
- Produce direct, source-grounded answers for common rules question shapes.
- Abstain when selected evidence is missing or insufficient.
- Use local model synthesis only after retrieval and answerability pass.
- Validate model output and fall back safely.
- Keep Discord output compact, cited, and paste-safe.

**Non-Goals:**
- Do not answer from full rulebooks or unbounded context.
- Do not use remote commercial APIs.
- Do not make the model responsible for selecting sources from scratch.
- Do not encode every Vampire rule manually as a hard-coded answer.

## Decisions

1. Introduce answer outlines.
   - The outline records stance, key claims, source IDs, and missing evidence before prose generation.
   - It is easier to validate than free-form text and gives the QA workbench a synthesis-stage object.

2. Use deterministic composers for simple shapes.
   - Timing, cost, definition, and clear yes/no questions can often be composed from structured evidence without a model.
   - This keeps the bot useful when the model is unavailable.

3. Use local model synthesis for nuanced shapes.
   - The model receives only selected evidence and the answer outline, not fallback context.
   - The validator checks citations, required stance, answer length, unsupported source labels, and insufficiency compliance.

4. Treat fallback as a quality state.
   - If a quality profile requires model synthesis and the model is unavailable, the bot should fail closed rather than silently produce a low-quality template answer.
   - Lite profile can still use deterministic fallback with a visible degraded-quality diagnostic.

## Risks / Trade-offs

- Model validation can reject usable prose. Mitigation: start strict for citations and unsupported claims, then tune with QA cases.
- Deterministic composers can become too rule-specific. Mitigation: implement generic answer shapes, not one-off rules.
- Better synthesis may expose retrieval gaps more clearly. Mitigation: this is expected and should feed the retrieval/corpus changes.

## Migration Plan

Existing bot configs continue to run. Lite mode can use deterministic synthesis. Standard/quality profiles can opt into local model synthesis once `provision-local-rag-quality-runtime` is applied. Existing answer traces gain new synthesis fields but keep prior top-level diagnostics for compatibility.

