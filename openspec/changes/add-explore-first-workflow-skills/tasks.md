## 1. Blueprint foundation

- [x] 1.1 Define the blueprint resource schema and add the default `city-by-night-v1` blueprint manifest plus note templates
- [x] 1.2 Add committed per-blueprint state handling under `.backet/state/blueprints/`, including explicit slot-remap tracking and default fallback resolution
- [x] 1.3 Add lightweight `backet` frontmatter handling for workflow-owned notes without requiring migration of existing vault notes

## 2. CLI blueprint commands

- [x] 2.1 Implement `backet blueprint apply <vault> <blueprint>` with bootstrapped-vault checks and non-destructive scaffolding behavior
- [x] 2.2 Implement `backet blueprint status <vault> <blueprint>` with human-friendly and deterministic JSON output, showing custom slot mappings and inherited defaults
- [x] 2.3 Report slot presence, missing targets, and next-priority gaps from committed blueprint state plus note inspection

## 3. Workflow skill pack

- [x] 3.1 Add the shared workflow-authoring guidance assets that encode discuss-before-write and rules-aware grounding conventions
- [x] 3.2 Add the `city-foundation` skill directory, register it in the skill-pack manifest, and keep it compatible with current Codex skill conventions
- [x] 3.3 Make `city-foundation` consume bounded vault context and bounded rules chunks through existing CLI retrieval commands before proposing selective write targets

## 4. Validation and release safety

- [x] 4.1 Add unit and integration tests for blueprint apply/status behavior, frontmatter ownership markers, idempotent re-runs, and portability across machines
- [x] 4.2 Add fixture-driven workflow validation that combines the sample vault with a synthetic ingested rules corpus, including ambiguous-rules handling
- [x] 4.3 Update documentation and release validation so skill install/update flows and the first workflow usage path are exercised before shipping
