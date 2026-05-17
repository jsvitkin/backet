## Context

RAG quality depends on both retrieval code and stored corpus quality. Current chunks can include large page headers, split system blocks, noisy section labels, and stale metadata. The existing audit flow focuses on extraction quality; it does not clearly answer "do I need to reindex, repair, or reingest?"

This change makes corpus maintenance explicit. It keeps source PDFs outside the repo and vault unless the user has already linked them for repair. It treats reindexing as the default repair for schema and metadata changes, and reingestion as a last resort.

## Goals / Non-Goals

**Goals:**
- Tell the user whether the corpus needs no action, reindex, OCR/manual repair, or reingest.
- Refresh retrieval metadata for existing chunks without source PDFs.
- Improve source-window cleanliness for answers and QA.
- Keep all repair actions bounded to per-vault `.backet/rules/` state.

**Non-Goals:**
- Do not normalize the full rules system into a database of powers and mechanics.
- Do not store original PDFs in the repo.
- Do not silently rewrite or discard ingested text without reporting the change.

## Decisions

1. Add a corpus health layer.
   - It will inspect the rules database for metadata schema versions, missing metadata, low-quality chunks, missing embeddings, section-kind distribution, and source-link availability.
   - It reports actions as `none`, `reindex`, `repair`, or `reingest`.

2. Separate metadata repair from source repair.
   - Metadata repair uses existing stored chunk text and can run anywhere.
   - Source repair/reingestion requires verified source PDFs or explicit relink/force behavior.

3. Improve answer windows during indexing and retrieval.
   - Retrieval metadata should identify headings, body windows, aliases, and evidence cues.
   - Answer snippets should avoid repeated page furniture and favor text near matched anchors.

4. Keep migration reversible.
   - Reindexing updates metadata tables and embeddings but does not alter stored source pages unless a repair command is explicitly invoked.

## Risks / Trade-offs

- More diagnostics can overwhelm users. Mitigation: human output groups findings into "run this command next" buckets.
- Some chunk cleanup requires re-splitting pages. Mitigation: first refresh metadata only, then report reingest candidates when split quality is the blocker.
- Source PDFs may be unavailable. Mitigation: report exact missing source paths/fingerprints and continue with degraded corpus status.

## Migration Plan

After implementation, run `backet rules audit <vault>` or the new corpus doctor command. Most vaults should only need `backet rules index <vault> --full`. The command will explicitly say when reingestion is required and which book/source path is affected.

