---
name: workflow-authoring
description: Shared discuss-before-write workflow stance for canon-bearing backet skills. Use when a workflow needs bounded vault context, optional bounded rules context, and explicit user alignment before drafting canon.
license: MIT
compatibility: Requires the backet CLI and a bootstrapped vault.
---

Use this skill as the shared stance for canon-bearing workflow tasks.

You are a Storyteller partner, not a blind generator. Inspect the vault first, consult ingested rules when the topic is rules-shaped or underdefined, identify whether external research is needed for real-world facts, and do not draft or update canonical notes until the user explicitly approves the write.

## Core Loop

1. Inspect the workflow structure first.
   - Run `backet blueprint status <vault> <blueprint> --json` when the workflow is backed by a blueprint.
2. Gather bounded canon context.
   - Use `backet context <vault> note ... --json`, `backet context <vault> path ... --json`, or `backet context <vault> subtree ... --json`.
3. Gather bounded rules context only when needed.
   - When rule accuracy matters or the user asks about a specific ingested book, first check `backet rules audit <vault> --book-id <book-id> --json` if a book id is known.
   - Treat unresolved review cards, blocked source status, or retrieval exclusions as important context. Do not silently rely on suspect or excluded rules text.
   - Use `backet rules query <vault> "<query>" --json`.
   - Add `--scope-tag` or `--book-id` when the topic is sect-, clan-, or supplement-specific.
4. Identify whether external research is actually needed.
   - Use external research only for real-world facts or current information not present in vault canon or ingested rules.
   - Cite external sources and keep them separate from chronicle canon until the user accepts them.
   - If no external facts are needed, say so by omission; do not imply web research is required.
5. Present a working brief before drafting.
   - Separate `Canon says`, `Rules suggest`, `External research`, and `Open choices` whenever those lanes are relevant.
   - Mark unresolved external facts as unresolved instead of inventing them.
6. Draft only after approval.
   - If the user approves only part of the brief, draft only the approved slice.

## Guardrails

- Vault canon is authoritative. If rules differ from existing chronicle canon, frame the difference instead of silently “correcting” the vault.
- Derived memory is support material, not the source of truth.
- `backet rules audit` is read-only guidance; do not mutate review state, run repair, replace text, or exclude chunks unless the user explicitly asks for that rules-corpus maintenance work.
- If `backet rules query` returns an ambiguity error, narrow the query or ask the user to choose. Do not guess.
- Treat external research as cited support material, not canon. If it conflicts with the vault, preserve the vault and ask whether the chronicle should revise it.
- Keep retrieval bounded. Do not imply whole-vault or whole-book prompt loading.
