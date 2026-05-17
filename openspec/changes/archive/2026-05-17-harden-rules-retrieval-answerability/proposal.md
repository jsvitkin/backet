## Why

The RAG v2 trace can report `answerable` even when selected chunks are mere mentions or generic lore. Medium and hard questions need stricter planning, retrieval, and answerability contracts before a stronger model can help.

## What Changes

- Preserve high-value terms and typo/legacy aliases such as `dementia` -> `dementation` and `bloodbond` -> `blood bond`.
- Replace broad OR-only exact retrieval with anchored retrieval that requires entity and intent terms to co-occur when the query has identifiable rules entities.
- Treat hash embeddings as degraded retrieval that cannot satisfy quality profiles by itself.
- Tighten evidence status so an answer is answerable only when selected evidence contains the requested entity, the relevant intent evidence, and enough source proximity.
- Demote or reject chunks that only mention the entity, only mention generic targeting words, or come from lore/sheet/table sections when the user asks for mechanics.
- Preserve fallback context for debugging, but do not pass fallback-only evidence as an answerable source packet.
- Add tests using the QA workbench cases as regression drivers.

## Capabilities

### New Capabilities

### Modified Capabilities
- `rules-query`: Query planning and answerability requirements become stricter and more transparent.
- `hybrid-rules-retrieval`: Retrieval channels must distinguish anchored evidence from broad fallback matches.
- `answer-quality-diagnostics`: Diagnostics must expose degraded retrieval and false-confidence reasons.

## Impact

- Affected CLI: `backet rules query`, bot runtime rule retrieval, and JSON trace payloads.
- Affected per-vault state: existing rules databases can be reindexed to refresh metadata; source PDFs are not stored or modified.
- Affected tests: retrieval unit tests, bot QA cases, and integration tests for ambiguous/insufficient evidence.
- Breaking behavior: some previously "answered" questions will now return insufficient evidence until the corpus or model services are improved. This is intentional fail-closed behavior for quality profiles.

