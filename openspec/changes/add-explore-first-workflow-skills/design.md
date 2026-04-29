## Context

`backet` now has the lower layers needed for authoring workflows: vault bootstrap, bounded vault retrieval, derived memory, and a private rules corpus with precedence-aware queries. What it does not yet have is a workflow layer that uses those substrates to help a Storyteller think through canon before writing it.

That gap matters because Vampire city design is highly interdependent. Tone, historical trauma, political order, feeding pressure, institutions, coteries, and named SPCs are not independent generators; they constrain one another. The sample Prague-by-Night vault in this repository's fixtures and the user's external example both reinforce a top-down pattern: broad city pressure comes before local cast details.

This change therefore needs to establish two things at once:

- a reusable contract for how workflow skills behave
- the first concrete workflow, `city-foundation`, that applies that contract to top-level city canon

It also needs a small amount of deterministic CLI help so skills do not guess note targets or filesystem conventions in free text.

## Goals / Non-Goals

**Goals:**

- Define an explore-first workflow contract shared by future authoring skills.
- Keep workflow skills thin by reusing existing `backet context`, `backet memory`, and `backet rules query` commands for bounded grounding.
- Add minimal blueprint support so the CLI can scaffold and inspect workflow note targets deterministically.
- Define the first workflow skill, `city-foundation`, around a narrow top-level slice of city canon.
- Preserve vault canon as authoritative while allowing workflow skills to consult rules and derived memory as bounded support layers.
- Keep CLI release cadence and skill-pack release cadence separable.

**Non-Goals:**

- Implement later lower-level workflows such as districts, factions, SPCs, plotlines, or session prep.
- Normalize rulebook content into a mechanics database or direct note-writing engine.
- Force one permanent global vault taxonomy beyond the default blueprint introduced here.
- Make workflow skills auto-write canon without an explicit user go-ahead.
- Replace existing retrieval commands with a new monolithic workflow-specific context API in this slice.

## Decisions

### 1. Treat workflow skills as conversational planners first and writing tools second

Every authoring workflow skill will follow the same default loop:

```text
inspect vault canon
  -> pull bounded rules context if needed
  -> present a working brief
  -> discuss tradeoffs and open choices
  -> draft or update canon only after approval
```

The brief should separate:

- `Canon says`
- `Rules suggest`
- `Open choices`

Why:

- This matches the user's preferred OpenSpec-like workflow stance.
- It reduces premature canon generation in a domain where one early choice ripples across many later notes.
- It keeps the skill useful both for empty vaults and for mature vaults that need refinement rather than wholesale generation.

Alternative considered:

- Prompt-first generation that writes notes immediately. Rejected because it encourages brittle canon and weakens the collaborative authoring posture.

### 2. Keep responsibilities split across skill pack, CLI, vault canon, and per-vault state

The responsibility split will be:

- **Skill pack**: conversational exploration, synthesis, user-facing brief framing, and final drafting once approved
- **CLI**: deterministic scaffolding, status inspection, bounded vault retrieval, derived memory rebuild, and rules retrieval
- **Vault notes**: canonical chronicle content
- **`.backet/` state**: committed workflow blueprint metadata, retrieval indexes, readable derived memory, and committed ingested rules corpus

Why:

- It preserves the project boundary where skills are the authoring layer and the CLI is the operational layer.
- It allows skill-pack iteration without coupling every workflow tweak to a CLI release.
- It keeps canon in the vault, not in skill metadata or opaque machine state.

Alternative considered:

- Making skills responsible for path discovery, note scaffolding, and raw corpus retrieval themselves. Rejected because it duplicates logic and fights the product architecture already established by earlier changes.

### 3. Reuse existing retrieval commands instead of adding a new workflow-brief command in v1

Workflow skills will compose existing CLI commands rather than depending on a new orchestration command in this change.

Expected primitives:

```text
backet context <vault> ...
backet memory build <vault> --family city
backet rules query <vault> ...
```

This means:

- bounded vault retrieval remains owned by the hybrid retrieval layer
- rules retrieval remains owned by the rules corpus layer
- workflow logic stays in the skill instead of creating a second, partially overlapping planner inside the CLI

Why:

- The existing retrieval layers already provide the bounded, machine-readable surfaces the skill needs.
- It keeps this change focused on workflow behavior and scaffolding rather than inventing a higher-level orchestration API too early.
- It preserves the rulebook precedence and ambiguity behavior already defined for `backet rules query`.

Alternative considered:

- Adding a new `backet workflow brief` command now. Rejected for this slice to keep the CLI surface narrow and avoid duplicating retrieval composition logic before more than one workflow skill exists.

### 4. Introduce repo-stored blueprint manifests plus committed per-vault blueprint state, with optional per-slot remapping

The CLI will gain a small blueprint subsystem with three initial responsibilities:

- scaffold default note targets for a named workflow blueprint
- allow explicit remapping of individual semantic slots when the user wants to diverge from the default layout
- report structural status for that blueprint in human-readable and machine-readable forms

Expected command shape:

```text
backet blueprint apply <vault> city-by-night-v1
backet blueprint status <vault> city-by-night-v1 --json
```

Blueprint definitions should live in the repository as resources, for example:

```text
src/backet/resources/blueprints/
  city-by-night-v1/
    manifest.yaml
    templates/
```

Committed per-vault blueprint state should live under `.backet/state/`, for example:

```text
.backet/state/blueprints/city-by-night-v1.json
```

That state should track:

- blueprint id and version
- semantic slot ids
- default or resolved note paths
- whether each resolved path is inherited from the blueprint default or explicitly remapped by the user
- creation timestamps
- structural status data needed for reporting

Why:

- Skills need deterministic targets without hardcoding repository-relative file paths in prompt text.
- Users can keep the default layout for untouched slots while overriding only the paths they actually want to customize.
- A blueprint manifest lets the project support more than one future information architecture without treating the Prague-style numbering as eternal law.
- Smaller per-blueprint state files keep the authoring surface portable across machines without forcing unrelated workflows into one shared registry.

Alternative considered:

- Requiring the skill to infer the workflow structure purely from existing folders. Rejected because blank or partially blank vaults need deterministic scaffolding, and mature vaults still benefit from explicit slot accounting.

### 5. Add lightweight `backet` frontmatter only to workflow-owned notes

Notes created by blueprint scaffolding or first written by workflow skills should carry a small ownership block such as:

```yaml
---
backet:
  blueprint: city-by-night-v1
  workflow: city-foundation
  slot: aesthetic-mood
---
```

This metadata is only for notes the workflow system owns. Existing legacy notes do not need to be rewritten to participate in retrieval.

Why:

- It gives status reporting and future workflow updates a stable ownership signal.
- It avoids forcing immediate frontmatter migration on the user's existing vaults.
- It supports future workflows that may need to distinguish skill-owned canonical notes from adjacent reference material.

Alternative considered:

- No note metadata at all. Rejected because status, drift detection, and future slot-aware updates become much harder once files are moved or edited.

### 6. Define `city-foundation` around semantic slots, with one default blueprint mapping in v1

The workflow capability is semantic first, not path first. In v1 the default `city-by-night-v1` blueprint will map a narrow set of top-level slots to default note paths inspired by the user's existing Prague structure:

- `aesthetic-mood`
- `historical-trauma-memory`
- `kindred-reputation`
- `human-cultural-tone`
- `present-night-pressure`

The default path mapping can be Prague-like, but the workflow contract itself is about the semantic slots, not about permanent folder numbering. If the user wants to place some slots elsewhere, the blueprint system should honor explicit remaps for those slots while continuing to use the default mapping for every slot that was not customized.

`city-foundation` explicitly stops before:

- detailed district buildout
- named faction rosters
- named SPC generation
- plotline authoring

Why:

- This gives one strong top-down workflow without overcommitting to the entire future skill tree.
- It reflects the observed order in both official city material and the user's example vault.
- It leaves later workflows room to build on stable top-level canon instead of rewriting around premature details.

Alternative considered:

- Starting with an NPC or district workflow. Rejected because those workflows depend too heavily on upstream city assumptions and would likely create churn.

### 7. Make canon precedence explicit: vault notes first, derived memory second, rules third

Workflow skills must treat sources in this order:

1. human-authored vault canon
2. derived memory and indexed retrieval support
3. bounded rule chunks and lore guidance from ingested PDFs

This means:

- rules are consulted when the topic is rules-shaped, lore-sensitive, or underdefined in the vault
- rules do not silently overwrite existing chronicle canon
- ambiguity from multiple supplement-specific sources must be surfaced rather than collapsed
- derived memory remains a retrieval aid, not a canonical rewrite surface

Why:

- The user explicitly wants rules-aware workflows, but the chronicle still owns its own truth.
- The rules subsystem already models supplement precedence and ambiguity; the workflow layer should preserve that honesty.
- This avoids a subtle but dangerous failure mode where a skill “corrects” intentional chronicle deviations back to baseline V5.

Alternative considered:

- Treating rules as globally authoritative over existing canon. Rejected because it would make later workflow runs unstable and disrespect the vault as source of truth.

### 8. Validate both the CLI contract and the skill contract

Testing should cover both halves of the system:

- CLI tests for blueprint apply/status behavior, JSON output shape, idempotent re-runs, and non-destructive handling of existing note files
- fixture-driven tests that combine a sample vault with indexed canon and a synthetic ingested rules corpus
- skill-pack tests that verify manifest registration, Agent Skills-compatible file layout, and the expected discuss-before-write posture in skill instructions
- install/update smoke coverage ensuring the new skill ships through the existing skill-pack distribution flow

Why:

- The risk here is not only broken code; it is also broken workflow posture.
- Blueprint status and skill packaging are both compatibility surfaces for future workflows.

Alternative considered:

- Testing only the CLI plumbing. Rejected because the authoring contract partly lives in skill-pack conventions and needs direct validation.

## Risks / Trade-offs

- [The first blueprint may overfit to the Prague-style numbered taxonomy] -> Keep the workflow semantic-slot-based and isolate the numbering inside the `city-by-night-v1` blueprint resource.
- [Discuss-first workflows may feel slow] -> Require skills to inspect existing canon before asking questions and to limit themselves to high-leverage open choices.
- [Rules retrieval may return noisy or conflicting material] -> Keep rules queries bounded, preserve book metadata and precedence, and surface ambiguity instead of guessing.
- [Frontmatter ownership markers may not fit legacy vaults cleanly] -> Apply them only to workflow-owned notes and do not require retroactive migration.
- [Blueprint status may be mistaken for content quality validation] -> Limit status to structural completion and clearly avoid claiming prose correctness or thematic quality.

## Migration Plan

1. Add blueprint resource format and CLI command surface for `apply` and `status`.
2. Add committed per-vault blueprint state handling under `.backet/state/blueprints/`.
3. Add workflow-owned note templates and lightweight frontmatter conventions.
4. Add the `city-foundation` skill plus skill-pack manifest entries.
5. Add tests for blueprint behavior, skill-pack structure, and workflow grounding against vault and rules fixtures.
6. Document the first workflow and the expected discuss-before-write posture.

Rollback would mainly involve removing or revising the blueprint subsystem and the first workflow skill before later authoring workflows depend on them. Because the skill pack ships separately from the CLI, a rollback can also happen at either layer independently if one surface proves stable before the other.

## Open Questions

- None for this slice.
