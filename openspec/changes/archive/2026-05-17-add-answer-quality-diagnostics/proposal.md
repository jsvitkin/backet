## Why

Recent Discord answers can look polished while being grounded in the wrong retrieved rule text. We need a repeatable way to see what the bot retrieved, why it ranked those sources, whether the sources actually answer the question, and whether future changes improve or regress answer quality.

## What Changes

- Add answer-quality diagnostics for bot playground and machine-readable bot answer flows.
- Add a small regression case format for real Discord questions, expected evidence, and expected refusal behavior.
- Add deterministic evaluation output that separates retrieval quality, answerability, and final answer quality.
- Keep diagnostics bounded to retrieved snippets and source metadata; do not dump full rulebooks, full vault sections, Discord secrets, or source PDFs.
- Make diagnostics useful before the RAG v2 work lands by reporting current retrieval and template behavior, while reserving fields for future query plans and evidence gates.

## Capabilities

### New Capabilities
- `answer-quality-diagnostics`: Trace, evaluate, and regression-test bot answers without exposing private corpus material beyond bounded retrieved evidence.

### Modified Capabilities

## Impact

- Affects CLI bot playground and bot ask JSON output.
- Affects bot runtime diagnostics and tests, but not Discord command authorization or response visibility.
- Adds repo test fixtures for representative answer-quality cases.
- Does not change the ingested rules corpus schema in this first slice.
- Does not copy source PDFs or model files into the repo or bot bundle.
- CLI and skill updates can ship independently: the CLI owns diagnostics and evaluation; skills may later call the diagnostic commands but do not embed diagnostic logic.
