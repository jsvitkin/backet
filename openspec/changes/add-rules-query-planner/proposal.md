## Why

Rules questions are currently passed into retrieval as raw user text, so ordinary wording such as "how do I learn Obfuscate" or "bloodbonds" can rank irrelevant chunks above the actual rule. A query planner is needed to normalize terms, infer intent, and ask retrieval for the kind of evidence the answer actually needs.

## What Changes

- Add a rules query planning stage before rules retrieval.
- Normalize aliases, plurals, compounds, and common table phrasing into canonical rules terms and scope tags.
- Classify question intent such as definition, advancement, targeting, cost, dice pool, consequence, or broad explanation.
- Generate multiple retrieval queries from the plan rather than relying on one raw FTS query.
- Expose the query plan in diagnostics so bad retrieval can be debugged and regression-tested.
- Keep the first implementation deterministic and local; no remote model call is required for planning.

## Capabilities

### New Capabilities

### Modified Capabilities
- `rules-query`: Rules queries gain a local planning stage that normalizes the question, extracts rule entities and scopes, and produces retrieval queries.

## Impact

- Affects rules query CLI behavior and Discord bot rules retrieval.
- Affects rule query diagnostics and answer-quality regression tests.
- Uses existing rules scope taxonomy as the first canonical vocabulary source.
- Adds no source PDF storage and no remote processing.
- Stores no canonical campaign content; query plans are transient diagnostics, not vault notes.
- CLI owns planning. Skills and Discord runtime consume planned retrieval behavior through existing CLI/runtime APIs.
