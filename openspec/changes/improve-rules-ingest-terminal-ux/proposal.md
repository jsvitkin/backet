## Why

`backet rules ingest` can spend a long time extracting and OCR-processing large rulebooks without printing anything, which makes a healthy ingest look dead. When ingestion completes, the human output also dumps raw diagnostic arrays, so the user has to interpret machine-shaped fields instead of seeing a readable status and next action.

## What Changes

- Add visible human-terminal progress for `backet rules ingest` while a rulebook is being inspected, extracted, OCR-processed, chunked, stored, indexed, and summarized.
- Ensure the command proves liveness quickly after invocation and continues to report progress or phase activity during long-running work.
- Preserve clean machine-readable `--json` output by keeping progress and human-only status out of stdout JSON.
- Replace unbounded human output for long lists such as OCR pages and suspect pages with bounded summaries, clearer labels, and actionable follow-up commands.
- Label non-normal ingestion outcomes in human terms, such as pages that required OCR, pages still needing review, low-confidence extraction, and indexing/storage completion.

### Non-Goals

- Do not change the rules ingestion data model, chunking behavior, rule precedence, query behavior, or audit semantics.
- Do not copy source PDFs into the vault or change where source PDFs live.
- Do not make skills responsible for reporting ingestion progress; this belongs to the CLI.
- Do not add remote telemetry, remote OCR, or remote PDF processing.
- Do not introduce normalized mechanics extraction or house-rule modeling.

## Capabilities

### New Capabilities

- `rules-ingest-terminal-ux`: Human-facing terminal visibility and completion reporting for rules ingestion commands.

### Modified Capabilities

- None.

## Impact

- CLI: affects `backet rules ingest` presentation, progress rendering, and human completion reporting.
- Rules ingestion internals: may need progress events or callbacks from the ingestion pipeline, but the persisted rules corpus remains unchanged.
- Per-vault state: no storage layout change; existing `.backet/rules/` data remains compatible.
- Source PDFs: remain external to the vault and are still processed locally.
- JSON/API surface: `--json` remains deterministic and complete; human progress must not corrupt JSON stdout.
- Dependencies: likely uses the existing Rich dependency for progress/status rendering rather than adding a new terminal UI dependency.
