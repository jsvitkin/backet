## Why

The current rules retriever is hybrid in name but still shallow: it merges exact and semantic candidates, then selects top chunks without a strong evidence model. To make bot answers materially smarter, rules retrieval needs a RAG v2 pipeline that gathers broader candidates, reranks them against the planned question, and reports whether the evidence actually answers the question.

## What Changes

- Add a rules RAG v2 retrieval pipeline after query planning.
- Generate candidates from planned exact queries, phrase/alias queries, semantic search, and metadata-aware filters.
- Rerank candidates using intent, entity coverage, source metadata, extraction quality, section kind, proximity, and answerability signals.
- Add an evidence gate that distinguishes answerable evidence from mere mentions.
- Improve retrieval metadata so chunks carry section structure, aliases, and evidence classifications needed by RAG v2.
- Report RAG v2 diagnostics in machine-readable rules query and bot answer traces.
- Keep retrieval bounded to top candidates; do not load whole rulebooks or whole vault sections into context.

## Capabilities

### New Capabilities

### Modified Capabilities
- `hybrid-rules-retrieval`: Existing hybrid retrieval is upgraded into a staged RAG v2 evidence pipeline.
- `rules-ingestion`: Ingested chunks gain additional retrieval-ready structure needed by RAG v2.
- `rules-query`: Rules query output gains RAG v2 evidence diagnostics and answerability metadata.

## Impact

- Affects rules database metadata, rules indexing, rules query output, bot runtime source selection, and tests.
- May require a lightweight rules metadata migration or rebuild path for existing rules stores.
- Continues to keep source PDFs external to the vault and out of bot bundles.
- Does not require a hosted LLM; optional stronger rerankers are enabled by the later hosting change.
- CLI owns retrieval and indexing. Skills and Discord consume bounded evidence packets through existing command/runtime surfaces.
