## Why

Vampire rulebooks carry mechanics, lore, and edge-case guidance that the model cannot be trusted to recall accurately on its own. `backet` needs a local way to ingest owned PDFs into a retrievable corpus so later skills can ask for the right chunks without requiring manual pre-processing by the user.

## What Changes

- Add a PDF-only ingestion pipeline for rulebooks supplied from local file paths.
- Add local extraction with OCR fallback for extraction-resistant PDFs.
- Add chunking and source metadata capture so rules can be queried consistently after ingestion.
- Add per-vault storage for ingested rule chunks under `.backet/` while keeping source PDFs external to the vault.
- Add an audit and targeted recovery loop for low-confidence OCR or bad chunking.
- Add precedence metadata and resolution behavior so supplement-specific rules can override core rules, with explicit user intervention when multiple specific sources conflict.

### Non-Goals

- Copy or store source PDFs inside the vault.
- Normalize the full rules corpus into a formal mechanics database.
- Add house rules or chronicle-specific rule overrides.

## Capabilities

### New Capabilities

- `rules-ingestion`: Ingest local rulebook PDFs into a per-vault chunk corpus with extraction, OCR fallback, and source metadata.
- `rules-query`: Retrieve raw rule chunks with source metadata and precedence-aware conflict handling.
- `rules-audit`: Audit ingestion quality, report suspect chunks, and support targeted recovery for failed or low-confidence spans.

### Modified Capabilities

- None.

## Impact

- Affects per-vault storage under `.backet/`, local OCR/extraction tooling, and rules retrieval behavior.
- Introduces book-level metadata and precedence handling that later workflow skills will depend on.
- Creates backup and Git trade-offs because ingested rule text is intended to travel with the vault while source PDFs remain external.
