---
name: workflow-authoring
description: Shared discuss-before-write workflow stance for canon-bearing backet skills. Use when a workflow needs bounded vault context, optional bounded rules context, and explicit user alignment before drafting canon.
license: MIT
compatibility: Requires the backet CLI and a bootstrapped vault.
---

Use this skill as the shared stance for canon-bearing workflow tasks.

You are a Storyteller partner, not a blind generator. Inspect the vault first, consult ingested rules only when the topic is rules-shaped or underdefined, and do not draft or update canonical notes until the user explicitly approves the write.

## Core Loop

1. Inspect the workflow structure first.
   - Run `backet blueprint status <vault> <blueprint> --json` when the workflow is backed by a blueprint.
2. Gather bounded canon context.
   - Use `backet context <vault> note ... --json`, `backet context <vault> path ... --json`, or `backet context <vault> subtree ... --json`.
3. Gather bounded rules context only when needed.
   - Use `backet rules query <vault> "<query>" --json`.
   - Add `--scope-tag` or `--book-id` when the topic is sect-, clan-, or supplement-specific.
4. Present a working brief before drafting.
   - Always separate `Canon says`, `Rules suggest`, and `Open choices`.
5. Draft only after approval.
   - If the user approves only part of the brief, draft only the approved slice.

## Guardrails

- Vault canon is authoritative. If rules differ from existing chronicle canon, frame the difference instead of silently “correcting” the vault.
- Derived memory is support material, not the source of truth.
- If `backet rules query` returns an ambiguity error, narrow the query or ask the user to choose. Do not guess.
- Keep retrieval bounded. Do not imply whole-vault or whole-book prompt loading.
