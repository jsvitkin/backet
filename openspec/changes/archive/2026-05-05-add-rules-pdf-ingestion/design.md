## Context

The intended `backet` workflows depend on rules and meta-lore that the base model does not remember reliably enough for Vampire play materials, especially when mechanical details or edge-case lore matter. The user wants to ingest several owned PDFs, potentially totaling hundreds of megabytes, and then back up the resulting ingested corpus with the vault so it does not need to be rebuilt after every machine change.

The rulebooks themselves remain outside the vault. This change is only about turning them into a local, queryable chunk corpus plus audit metadata.

## Goals / Non-Goals

**Goals:**

- Ingest local PDF rulebooks into per-vault state.
- Support direct extraction plus OCR fallback.
- Persist raw chunk corpus and source metadata for later retrieval.
- Add audit and targeted recovery for low-confidence ingestion.
- Add book-aware precedence rules for core versus supplement behavior.

**Non-Goals:**

- Store source PDFs inside the vault.
- Build a normalized mechanics database or full rule-card layer.
- Add house-rule override support.

## Decisions

### 1. Accept PDF input only for v1

This change will ingest rulebooks from PDF paths only.

Why:

- It matches the user's actual source format.
- It keeps the first ingestion boundary narrow and testable.

Alternative considered:

- Supporting arbitrary text or document formats in the same change. Rejected because it broadens ingestion too early.

### 2. Keep source PDFs external and store only ingested corpus under `.backet/`

The original PDFs will remain on disk wherever the user keeps them. `backet` will store only the ingested results under `.backet/rules/`.

Why:

- It keeps the vault from becoming a raw document dump.
- It still satisfies the user's backup goal for the ingested rule corpus.

Alternative considered:

- Copying source PDFs into the vault. Rejected because it is unnecessary for retrieval and backup goals.

### 3. Use a staged ingestion pipeline with OCR fallback

The pipeline will be:

```text
inspect PDF
  -> direct text extraction
  -> local OCR fallback for failed/weak regions
  -> structure detection
  -> chunking
  -> metadata tagging
  -> storage and indexing
```

Why:

- Some official PDFs extract cleanly while others do not.
- A staged pipeline keeps clean PDFs cheap and bad PDFs recoverable.

Alternative considered:

- OCR-everything by default. Rejected because it is slower and loses text quality where native extraction already works.

### 3a. Use PyMuPDF plus Tesseract as the default local extraction and OCR stack

The default local rules-ingestion stack will be:

- `pymupdf` for PDF inspection, direct text extraction, and page rendering
- `tesseract` as the OCR engine for pages or spans that need fallback OCR

`ocrmypdf` will not be a required default dependency in v1.

Why:

- PyMuPDF covers direct extraction and page rendering in one Python-facing library.
- PyMuPDF also supports OCR-assisted extraction flows while Tesseract remains the underlying local OCR engine.
- This keeps the v1 dependency stack simpler than requiring OCRmyPDF, Ghostscript, and other heavier system dependencies from the start.

Alternative considered:

- OCRmyPDF as the default pipeline. Rejected because it adds a heavier system dependency chain before we know it is necessary.
- Poppler-first extraction via `pdftotext`. Rejected as the default because PyMuPDF gives one cleaner Python-native control surface for both extraction and rendering.

### 4. Treat raw chunk retrieval as the primary output for this change

This change will store and return raw chunks with rich source metadata, not a normalized mechanics layer.

Why:

- It keeps the scope manageable.
- It preserves fidelity to the original books while giving later changes something reliable to build on.

Alternative considered:

- Full rule normalization in the same change. Rejected because it is a much larger modeling problem and the user explicitly agreed to defer it.

### 5. Add explicit book metadata and precedence tiers

Every ingested book will carry metadata sufficient to support precedence decisions such as:

- core rulebooks as fallback sources
- supplement-specific books preferred when they are more specific
- explicit ambiguity when multiple specific supplements conflict

Why:

- The user's books are not flat; supplements refine or override core material.
- Retrieval needs to know more than just "which chunk matched."

Alternative considered:

- Ranking all books equally. Rejected because it ignores the real rule hierarchy.

### 5a. Use a dedicated committed rules store under `.backet/rules/`

The ingested rules corpus will live in a dedicated durable store under `.backet/rules/`, separate from the vault retrieval database.

Why:

- The rules corpus has a different lifecycle, size profile, and audit surface than vault Markdown indexing.
- Keeping it separate makes targeted repair and future rules-specific migrations safer.
- It avoids inflating the vault retrieval database with book-specific provenance and OCR artifacts.

Alternative considered:

- Storing all rules metadata in the main vault retrieval DB. Rejected because it couples two corpora that will evolve and be repaired differently.

### 5b. Use book identity, tier, and scope tags as the minimum classification metadata

Two flags alone are not enough. The minimum useful book-classification metadata at ingest time will be:

- `book_id`
- `book_title`
- `tier` with values such as `core` or `supplement`
- `scope_tags` describing what the supplement is specific to, such as `camarilla`, `clan`, `discipline`, or other system areas

Why:

- A simple core-versus-supplement flag identifies precedence class, but not which supplement is being cited.
- Conflict handling between multiple specific supplements needs both book identity and scope.
- This stays small while still supporting the agreed precedence rule: specific over core, and ask the user when multiple specific sources conflict.

Alternative considered:

- A single boolean or pair of flags. Rejected because it cannot support meaningful ambiguity reporting across multiple specific books.

### 6. Make auditability first-class

The ingestion pipeline will retain confidence and structure-quality signals so the user can inspect bad OCR or broken chunks later.

Why:

- PDF ingestion quality is the riskiest part of this change.
- A visible audit loop is better than pretending the ingest is always clean.

Alternative considered:

- Silent best-effort ingest. Rejected because it hides quality failures that matter later.

### 7. Validate ingestion with synthetic and fixture-based tests

This change will require:

- unit tests for precedence metadata, ambiguity handling, and chunk metadata
- integration tests for direct extraction, OCR fallback, and targeted recovery
- CI-safe fixture PDFs that exercise the pipeline without depending on private owned books

Why:

- OCR and extraction failures are exactly the kind of regressions that hide until late if they are not exercised in automation.
- The user explicitly wants release validation to catch install and post-install issues before shipping.

Alternative considered:

- Depending on manual testing with private books. Rejected because it is not reproducible in CI and will miss release regressions.

## Risks / Trade-offs

- [OCR quality may vary heavily across books] -> Keep targeted audit and reprocessing in scope from day one.
- [Committed ingested rule corpus can create large diffs] -> Keep scratch artifacts ignored and structure durable stored output carefully.
- [Book precedence metadata may still be incomplete in edge cases] -> Surface ambiguity rather than guessing when specific sources conflict.
- [Raw chunks are less convenient than normalized mechanics] -> Treat this as an intentional first step and defer normalization to a later change.
- [PDF ingestion regressions may only surface on awkward documents] -> Maintain CI-safe fixture PDFs that cover clean extraction, OCR fallback, and targeted repair flows.

## Migration Plan

1. Define the per-vault storage layout for ingested rule corpus and audit data.
2. Implement PDF inspection, extraction, OCR fallback, and chunk storage.
3. Add book metadata and precedence handling.
4. Add query and audit commands plus targeted recovery.

Rollback would mainly involve adjusting the stored chunk schema or metadata model before later workflow features depend on it.

## Open Questions

- Should `backet doctor` install-missing-dependency guidance prefer Homebrew commands on macOS and package-manager guidance elsewhere?
- Which parts of per-book audit history should be kept durably versus treated as rebuildable scratch metadata?
