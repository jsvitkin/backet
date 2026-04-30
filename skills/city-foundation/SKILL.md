---
name: city-foundation
description: Explore and selectively draft the top-level city canon for a Vampire chronicle. Use after applying or inspecting the `city-by-night-v1` blueprint.
license: MIT
compatibility: Requires the backet CLI, a bootstrapped vault, and the workflow-authoring stance.
---

Use this skill to build or refine the city-wide foundation before districts, factions, named SPCs, or plotlines.

## Target Slots

The `city-by-night-v1` blueprint defines these top-level slots:

- `aesthetic-mood`
- `historical-trauma-memory`
- `kindred-reputation`
- `human-cultural-tone`
- `present-night-pressure`

## Start Here

1. Inspect the blueprint state.
   - Run `backet blueprint status <vault> city-by-night-v1 --json`.
2. If the user wants scaffolding and the targets are missing, apply the blueprint first.
   - Run `backet blueprint apply <vault> city-by-night-v1`.
   - Use `--slot-path slot-id=relative/path.md` only for slots the user explicitly wants to remap.
3. Gather bounded canon for the slots that already exist.
   - Use `backet context <vault> path "<resolved-path>" --json` for slot-level context.
   - Use `backet context <vault> subtree "1. City Identity & Thematic Structure" --json` when the city identity notes already exist and the workflow needs a broader read.
4. Pull rules only when the topic needs them.
   - Example Camarilla query: `backet rules query <vault> "prince praxis elysium feeding rights" --scope-tag camarilla --json`
   - Example Anarch query: `backet rules query <vault> "baron territory feeding enforcement" --json`
5. Identify any real-world facts that need external research.
   - Use this for city history, geography, neighborhoods, architecture, demographics, transport, or current local details not already grounded in the vault.
   - Keep researched facts cited and separate from canon until the user approves the chronicle choice.
6. Present the brief before drafting.
   - `Canon says`
   - `Rules suggest`
   - `External research`
   - `Open choices`

## Writing Rules

- Do not draft until the user explicitly says to proceed.
- If some slots already contain canon, refine those notes instead of duplicating them elsewhere.
- If the user approves only one or two slots, update only those slots and leave the rest in discussion mode.
- If rules conflict with vault canon, preserve the vault and frame the difference as a chronicle choice or a revision question.
- If rules retrieval is ambiguous, stop and ask for a narrower query or a user choice before drafting.
- If external research conflicts with vault canon, keep the vault authoritative and present the conflict as a deliberate chronicle choice.

## Boundaries

This workflow stops before:

- detailed district buildout
- named faction rosters
- named SPC generation
- plotline authoring
