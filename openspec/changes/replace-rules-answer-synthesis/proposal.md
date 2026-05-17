## Why

The current template answerer is a sentence picker. It can quote a plausible source without resolving the user's actual question, and it cannot combine nearby evidence into a direct answer. Once retrieval is stricter, answer synthesis must become source-grounded reasoning instead of source-adjacent extraction.

## What Changes

- Replace the rules answer template path with a grounded synthesis pipeline that consumes answer packets, evidence roles, and source anchors.
- Generate direct answer stances first: yes/no, definition, procedure, timing, cost, consequence, or insufficient evidence.
- Build answer outlines from selected evidence before final prose generation.
- Use local model synthesis when configured, with deterministic validation and fallback.
- Add a deterministic non-model composer for simple answer shapes and for fail-closed fallback.
- Remove narrow hard-coded answer helpers as the primary strategy; keep only broadly valid formatting utilities.
- Validate final answers for required stance, citations, unsupported claims, and source coverage.

## Capabilities

### New Capabilities

### Modified Capabilities
- `discord-query-bot`: Bot answers must be produced from grounded answer packets with explicit answer classes and citations.
- `answer-quality-diagnostics`: Diagnostics must show synthesis decisions, answer outline, validation results, and fallback reasons.

## Impact

- Affected code: `bot_answers.py`, bot runtime traces, local model prompt/validation, Discord response formatting.
- Affected configuration: `answer_mode` remains supported, but quality profiles can require model synthesis or fail closed.
- Affected tests: answer-shape tests, source-grounding tests, QA workbench cases, model fallback tests.
- User-visible behavior: medium/hard questions should produce direct answers or honest insufficiency instead of generic source quotes.

