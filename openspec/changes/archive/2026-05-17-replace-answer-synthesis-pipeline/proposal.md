## Why

The current answer formatter extracts sentences from selected chunks and can present irrelevant evidence as a confident answer. Once retrieval provides vetted evidence packets, the bot needs an answer synthesis pipeline that respects evidence status, refuses insufficient sources, and formats concise Discord answers without inventing unsupported claims.

## What Changes

- Replace direct sentence-picking as the primary answer path with evidence-aware answer synthesis.
- Add an answer packet contract between retrieval and response generation.
- Make insufficient, ambiguous, and conflicting evidence first-class response outcomes.
- Keep deterministic template fallback, but make it evidence-status aware rather than raw chunk driven.
- Guard local model output with citation and support validation.
- Keep Discord responses compact, citation-bearing, and safe from unwanted mentions.

## Capabilities

### New Capabilities

### Modified Capabilities
- `discord-query-bot`: Bot answer generation becomes evidence-aware and must refuse or clarify when retrieved sources do not answer the question.

## Impact

- Affects bot answer generation, bot runtime diagnostics, Discord formatting, and answer-quality tests.
- Depends on diagnostics from `add-answer-quality-diagnostics`; benefits most from evidence packets from `build-rules-rag-v2-retrieval`.
- Does not change rules ingestion or source PDF handling.
- Does not require a remote model; local model synthesis remains optional and guarded.
- CLI owns answer synthesis. Skills can rely on bot/CLI answer behavior but should not embed answer prompts.
