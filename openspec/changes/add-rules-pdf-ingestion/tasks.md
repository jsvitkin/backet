## 1. Rules corpus foundation

- [x] 1.1 Define the per-vault storage layout for ingested rule chunks, book metadata, and audit metadata under `.backet/rules/`
- [x] 1.2 Add the book registry model needed to distinguish core and supplement-specific sources
- [x] 1.3 Add tests or fixtures representing clean PDFs and extraction-resistant PDFs

## 2. Ingestion pipeline

- [x] 2.1 Implement PDF inspection and direct text extraction from local file paths
- [x] 2.2 Implement local OCR fallback for failed or weak extraction scopes
- [x] 2.3 Implement chunking and source-metadata persistence for ingested rules

## 3. Rules query and precedence behavior

- [x] 3.1 Implement raw chunk retrieval with machine-readable output including source metadata
- [x] 3.2 Implement precedence handling so supplement-specific rules outrank core fallback rules
- [x] 3.3 Implement ambiguity handling for conflicting specific sources

## 4. Audit and recovery

- [x] 4.1 Record ingestion confidence and structural quality markers during extraction and OCR
- [x] 4.2 Implement a rules audit command that reports suspect books, pages, or chunks
- [x] 4.3 Implement targeted repair and re-ingestion for selected books, sections, or page ranges

## 5. Ingestion quality coverage

- [x] 5.1 Add unit tests for precedence classification, chunk metadata generation, and ambiguity detection
- [x] 5.2 Add integration tests for direct extraction, OCR fallback, and targeted recovery flows
- [x] 5.3 Add install-safe smoke fixtures so ingestion dependencies and commands are exercised in CI without requiring real private rulebooks
