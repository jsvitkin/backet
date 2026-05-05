## Why

`backet rules audit` currently exposes useful ingestion-quality diagnostics as raw nested data, leaving the user to infer which findings are harmless, which are actionable, and how to resolve them. The rules corpus now has enough OCR, retrieval metadata, source PDF, and generated scope state that audit needs to become a guided human review workflow rather than a diagnostic dump.

## What Changes

- Replace non-JSON `backet rules audit` output with a bounded human summary that separates:
  - automatic maintenance issues, such as missing or stale semantic/retrieval metadata
  - reviewable extraction cases, such as low-confidence OCR on pages that may contain usable rules or lore
  - notices, such as OCR fallback on pages that passed quality checks or likely art/title/blank/index pages
  - source PDF status, including whether the stored PDF path exists and whether repair can safely rescan it
- Add a guided review flow for audit findings with explicit human decisions:
  - accept weird but usable extracted text
  - ignore expected non-rules material
  - exclude retained-but-useless text from rules retrieval
  - retry local extraction/OCR repair from the stored source PDF
  - replace failed OCR with human-provided corrected page text
  - skip for later without losing the finding
- Treat non-JSON `backet rules audit` as the human-first entry point, while preserving deterministic JSON and explicit non-interactive inputs for agents, tests, and scripts.
- Add automatic repair for cases the CLI can solve without user judgment:
  - refresh missing/stale semantic embeddings and retrieval metadata
  - retry extraction/OCR for selected pages when the stored source PDF is available and matches the ingested fingerprint
  - classify obvious art/title/blank/index noise as low-priority notices or suggested ignores
- Persist audit review decisions in the per-vault rules store so unchanged accepted/ignored/excluded findings do not keep returning as urgent work.
- Add source-PDF relink/status behavior for repair-blocking cases where the saved PDF path is missing or no longer matches the ingested fingerprint.
- Improve `backet rules scope audit` human output enough to fit the same mental model: summary first, reviewable scope suggestions second, machine-readable manifest/export/apply guidance only when needed.
- Preserve deterministic full-detail `--json` output for agents and scripts.

### Non-Goals

- Do not copy source PDFs into the vault; source PDFs remain external user-owned files.
- Do not send PDF pages, OCR text, or rule chunks to remote OCR or hosted model services.
- Do not build a normalized mechanics database or canonical rule-card system.
- Do not make skills responsible for modifying the rules corpus; review and repair actions belong to the CLI.
- Do not turn scope suggestions into automatic canon or Obsidian notes.
- Do not load whole rulebooks into context during audit or review; all review surfaces must remain bounded to selected books, pages, chunks, and summaries.

## Capabilities

### New Capabilities

- `rules-audit-review-flow`: Human-friendly audit summaries, guided review decisions, automatic local repair, source PDF status/relink behavior, and durable per-vault audit review state for ingested rulebooks.

### Modified Capabilities

- None.

## Impact

- CLI: affects `backet rules audit`, `backet rules repair`, `backet rules index`, and `backet rules scope audit`; likely adds review/relink subcommands or options under `backet rules`.
- Rules ingestion internals: uses existing page audit, chunk confidence, retrieval metadata, source PDF path, and fingerprint data; may add durable review decision and source relink records.
- Per-vault state: stores review decisions, manual page text overrides, retrieval exclusion state, and source PDF relink metadata under `.backet/rules/`; this is durable rules-corpus state that can be backed up with the vault.
- Source PDFs: remain external to the vault and are only referenced by stored path and fingerprint; automatic repair is available only when the source can be found and verified.
- Retrieval behavior: excludes or downranks human-excluded chunks and refreshes affected retrieval metadata after repair or replacement without widening query scope beyond indexed chunks.
- Skill pack: may update authoring guidance to interpret audit status before relying on rules retrieval, but CLI and skill updates can ship independently.
- JSON/API surface: `--json` remains deterministic and complete; human review prompts and summaries must not corrupt JSON stdout.
- Dependencies: should reuse local PyMuPDF, Tesseract, SQLite, and Rich; any OCR preprocessing should prefer existing/local dependencies unless a narrow additional dependency is justified.
