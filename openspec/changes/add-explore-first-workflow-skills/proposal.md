## Why

`backet` now has vault bootstrap, retrieval, memory, and rules-ingestion foundations, but it still lacks the first real authoring workflow that turns those substrates into guided city-building. The next step is to define how workflow skills should think with the user before writing canon, while grounding that conversation in both existing vault notes and bounded rulebook context.

## What Changes

- Add a shared explore-first workflow contract for authoring skills so they inspect canon, pull relevant rules as needed, discuss tradeoffs, and only write after user alignment.
- Add the first concrete workflow capability, `city-foundation`, for creating or refining top-level city canon before lower-level districts, factions, or named SPCs.
- Add minimal CLI support for deterministic workflow scaffolding and status reporting so skills can discover expected note targets and missing high-priority gaps without hardcoding one vault layout.
- Define how workflow skills use bounded retrieval across vault canon, derived memory, and ingested rules chunks without implying whole-vault or whole-book prompt loading.
- Keep the skill layer and CLI layer separately releasable: the CLI owns scaffolding, inspection, and machine-readable reporting, while the skill pack owns the conversational authoring workflow and can iterate independently.

## Capabilities

### New Capabilities
- `workflow-authoring`: Shared contract for explore-first, rules-aware workflow skills that discuss before writing and use bounded vault and rules context.
- `city-foundation`: First top-down city-building workflow for authoring high-level city canon such as mood, history, reputation, and present-night pressure.
- `vault-blueprints`: Deterministic CLI support for scaffolding and inspecting workflow-oriented vault targets without forcing skills to infer structure from scratch.

### Modified Capabilities
- None.

## Impact

- Affected systems: CLI command surface, skill pack contents, per-vault workflow scaffolding metadata, context assembly flows, and future skill-pack release practices.
- Likely code areas: [src/backet/cli.py](/Users/jansvitkin/projects/backet/src/backet/cli.py), new workflow modules under `src/backet/`, skill-pack manifest and new skill directories under `skills/`, and tests for CLI workflow contracts plus skill fixture behavior.
- Per-vault state impact: new committed workflow blueprint or status artifacts may live under `.backet/`, while machine-specific scratch remains ignored under `.backet/.gitignore`.
- Rules impact: ingested rule PDFs remain external to the vault; workflow skills retrieve only bounded raw chunks and source metadata from the committed rules corpus under `.backet/rules/`.
