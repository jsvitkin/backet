## Why

Rulebooks are not cleanly scoped at book level: a sect supplement can introduce clans, rituals, loresheets, institutional mechanics, and in-world perspectives on other sects. The current repeatable `--scope-tag` flag puts too much responsibility on the user and makes later retrieval precedence depend on blunt book-level metadata.

This change makes rules ingestion automatically derive reviewable page, section, and chunk scope assertions with evidence so `backet rules ingest` can remain a single command while retrieval gains finer authority signals.

## What Changes

- Add automated scope assertion generation during `backet rules ingest`, using PDF outline, page headings, section labels, controlled aliases, and mechanics/lore markers.
- Store generated scope assertions in the per-vault rules corpus under `.backet/rules/`, separate from external source PDFs and separate from canonical Obsidian vault notes.
- Apply high-confidence assertions to ingested rule chunks while preserving evidence, confidence, and role metadata for auditability.
- Add a review/audit surface for generated rule scopes so uncertain or surprising assertions can be inspected and corrected without re-ingesting the original PDF.
- **BREAKING**: Remove manual `--scope-tag` input from `backet rules ingest`; ingestion must infer source and span scopes automatically, and corrections happen through the scope review/apply workflow.
- Use scope assertion roles such as mechanical authority, setting/lore authority, and in-world perspective so a book that mentions a topic does not automatically outrank a topic-specific source.
- Keep rules retrieval bounded to indexed chunks and metadata filters; this does not imply loading whole rulebooks or whole PDFs into model context.
- Non-goals for the initial slice:
  - No remote AI or hosted model calls for private rulebook text.
  - No full normalized mechanics database.
  - No requirement that users hand-author complete scope manifests before ingestion.
  - No Obsidian note generation from rulebook contents.

## Capabilities

### New Capabilities
- `rules-scope-assertions`: Automatic generation, storage, review, and retrieval use of page/section/chunk scope assertions for ingested rulebooks.

### Modified Capabilities
- `rules-ingest-terminal-ux`: Human ingest output must summarize generated/applied scope assertions and review needs without dumping unbounded manifest data.

## Impact

- CLI: affects `backet rules ingest`, `backet rules query`, and likely adds `backet rules scope` review/update commands.
- Rules ingestion internals: adds generated source/span assertions, assertion confidence/evidence, chunk-level scope application, and export-on-demand manifests.
- Rules retrieval: uses chunk/page/section scope assertions for filtering, ranking, supplement precedence, and ambiguity handling instead of relying only on book-level tags.
- Per-vault state: committed durable scope assertions live under `.backet/rules/`; source PDFs remain external; temporary classifier scratch data remains ignored/rebuildable.
- Skills: authoring skills may consume richer rules query metadata, but the normal ingestion workflow remains in the CLI and can ship independently from skill-pack updates.
