## 1. Corpus Health Model

- [x] 1.1 Add a corpus health analyzer for rules database metadata, embeddings, section quality, source-link status, and reingest candidates.
- [x] 1.2 Add result categories for none, reindex, repair, and reingest.
- [x] 1.3 Add unit tests for each corpus health category.

## 2. Reindex and Repair Commands

- [x] 2.1 Extend `rules index --full` reporting to distinguish metadata refresh, embedding refresh, and source-free operation.
- [x] 2.2 Add or extend a rules audit/corpus doctor command that gives one next action per book.
- [x] 2.3 Ensure source PDF access is only required for OCR repair, relink, or reingestion paths.

## 3. Metadata and Window Quality

- [x] 3.1 Improve section-kind detection for page furniture, sheets, lore, headings, and mechanical system blocks.
- [x] 3.2 Improve source-window selection around matched anchors and evidence cues.
- [x] 3.3 Add tests for noisy headers, split system blocks, and clean excerpts.

## 4. Prague Vault Assessment

- [x] 4.1 Run the corpus health command against `E:/Projects/prague-by-night`.
- [x] 4.2 Report whether Prague needs reindexing, source repair, or reingestion before changing source data.
- [x] 4.3 If reingestion is required, list the exact books and source PDFs needed.

## 5. Validation

- [x] 5.1 Run the rules QA workbench after corpus repair.
- [x] 5.2 Add regression tests proving reindexing fixes stale metadata without source PDFs.
- [x] 5.3 Add human-output tests proving repair reports do not dump raw dict/list payloads.
