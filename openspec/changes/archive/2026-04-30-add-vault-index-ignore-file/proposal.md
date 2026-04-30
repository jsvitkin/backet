## Why

Existing Obsidian vaults can contain plugin files, templates, archived notes, generated exports, and other Markdown that should not become campaign canon. `backet index` needs a user-editable vault policy so it can adapt to each vault's shape without adding many CLI flags or hardcoded exclusions.

This matters now because `backet` is intended to initialize inside mature manually maintained vaults, where the index is a derived retrieval surface over human canon rather than an ingestion pipeline that owns the source files.

## What Changes

- Add a root-level `.backetignore` file that controls which Markdown paths are excluded from vault indexing.
- Generate a default `.backetignore` during `backet init` with sensible exclusions for tool state, Obsidian/system folders, and common support-note folders.
- Teach `backet doctor --fix` to restore a missing `.backetignore` using the default template without overwriting an existing user-edited file.
- Update the Markdown index scanner so ignored notes are left out of the corpus and previously indexed notes are removed on the next index refresh.
- Keep the index ignore policy separate from `.backet/.gitignore`, which remains scoped to Git behavior for Backet-owned state.
- Preserve bounded retrieval behavior: context commands continue to retrieve from the indexed corpus only, not from whole vault folders or ignored files.

Non-goals for this slice:

- Do not add a broad set of include/exclude CLI arguments.
- Do not make skills parse vault files or apply ignore rules themselves.
- Do not use `.backetignore` to control rulebook PDF ingestion; external PDFs and the ingested rules corpus remain separate from vault Markdown indexing.
- Do not rewrite, move, delete, or normalize user-authored vault notes.
- Do not require a specific Prague-style numbered taxonomy or any particular Obsidian folder layout.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `vault-indexing`: Vault indexing must honor a user-editable ignore policy before parsing, chunking, embedding, or storing Markdown notes.
- `vault-bootstrap`: Vault initialization and safe repair must manage the default index ignore policy separately from scoped Git ignore behavior.

## Impact

- CLI: `backet init`, `backet doctor`, `backet index`, and any command that refreshes or depends on the index.
- Per-vault content: a new root-level `.backetignore` file lives in the Obsidian vault and is intended to be committed with the vault as human-editable indexing policy.
- Per-vault state: ignored files do not appear in `.backet/state/vault-index.sqlite3`; stale rows for newly ignored paths are removed during reindexing. Existing `.backet/.gitignore` continues to ignore machine-specific scratch such as `cache/`, `temp/`, and `ocr-work/`.
- Skills: no required skill-pack behavior change; skills continue to call CLI retrieval surfaces and receive bounded source metadata from the indexed corpus.
- Rules corpus: no change to `backet rules ingest`; source PDFs still stay outside the vault and extracted rule chunks remain under `.backet/rules/`.
- Dependencies: implementation may add a small gitignore-pattern matching dependency such as `pathspec`, or an equivalent local parser if dependency cost is rejected during implementation.
