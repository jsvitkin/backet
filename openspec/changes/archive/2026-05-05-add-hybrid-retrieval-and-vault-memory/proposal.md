## Why

The vault and campaign canon will quickly outgrow anything that can be loaded directly into model context. `backet` needs a retrieval layer that can search, scope, and assemble bounded context from the vault without treating the entire note corpus as prompt text.

## What Changes

- Add Markdown-only vault indexing for per-vault campaign content.
- Add hybrid retrieval that combines exact search, semantic retrieval, metadata filters, and hierarchy-aware expansion.
- Add bounded context-bundle commands that return scoped context for agent workflows and human inspection.
- Add derived memory capsules under `.backet/` that summarize reusable context layers while staying rebuildable from canonical notes.
- Add stale-state detection so `backet` can recognize when the vault changed outside its own commands and recover safely.

### Non-Goals

- Ingest PDFs or non-Markdown attachments from the vault itself.
- Add workflow-specific authoring skills or note generators.
- Normalize game mechanics or ingest private rulebooks in this change.

## Capabilities

### New Capabilities

- `vault-indexing`: Index Markdown vault content into committed per-vault state and detect when that state is stale after external edits.
- `context-bundles`: Assemble bounded context packets from the indexed vault with deterministic machine-readable output when requested.
- `derived-memory`: Persist scoped, human-readable memory capsules under `.backet/` while preserving the vault notes as canonical source material.

### Modified Capabilities

- None.

## Impact

- Affects per-vault storage, indexing workflow, retrieval UX, and agent-facing context assembly.
- Introduces a committed index/state layer under `.backet/` plus ignored rebuildable artifacts.
- Creates the retrieval substrate that later rules-ingestion and authoring-workflow changes will rely on.
