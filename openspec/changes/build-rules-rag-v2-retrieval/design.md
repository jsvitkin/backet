## Context

The current retriever combines exact FTS rows and semantic rows, assigns a score, applies some quality penalties, and returns primary/fallback results. That is a useful foundation, but it does not model the difference between:

- a definition of a mechanic
- an incidental mention of a term
- a page listing a character's disciplines
- system text for a power
- advancement rules explaining how a power is learned
- targeting text explaining what subjects a power can affect

RAG v2 makes evidence selection explicit:

```text
query plan
  -> candidate generation
     -> exact / phrase / alias / semantic / metadata
  -> candidate normalization
  -> reranking
  -> evidence gate
  -> evidence packet
```

This change still operates over the private, local rules corpus under `.backet/rules/`. Source PDFs remain external. Bot bundles receive read-only retrieval artifacts, not source PDFs or rebuild caches.

## Goals / Non-Goals

**Goals:**
- Retrieve evidence that answers the question, not merely chunks containing overlapping words.
- Combine exact, semantic, alias, and metadata signals in a staged pipeline.
- Support answerability diagnostics: sufficient, insufficient, ambiguous, or conflicting.
- Preserve source metadata, precedence, and ambiguity handling.
- Improve chunk metadata enough for reranking and answerability.
- Keep runtime context bounded and inspectable.

**Non-Goals:**
- Do not rewrite final Discord answer prose in this change.
- Do not require paid hosting or remote APIs.
- Do not build a complete normalized rule database of every VTM mechanic.
- Do not store source PDFs in the vault or bundle.
- Do not remove existing exact-only fallback behavior until replacement coverage is proven.

## Decisions

### Decision: Introduce an evidence packet as retrieval output

Rules retrieval should return a structured evidence packet in addition to raw results. The packet should include:

- query plan reference
- candidate counts by retrieval channel
- selected evidence chunks
- fallback/context chunks
- rejected high-scoring chunks with rejection reasons
- evidence status: `answerable`, `insufficient`, `ambiguous`, or `conflicting`
- evidence needs satisfied or missing
- retrieval mode and backend diagnostics

Rationale: final answer generation should consume vetted evidence and status, not a flat list of chunks.

Alternative considered: continue returning only `primary_results` and `fallback_results`. That keeps compatibility but forces every answer layer to rediscover whether a source actually answers the question.

### Decision: Candidate generation should be broad, reranking should be strict

The retriever should gather a broader pool than the final answer needs, such as top 50 candidates across:

- planned exact terms
- exact phrase queries
- canonical alias queries
- semantic vector search
- scope and metadata filters
- raw query fallback

Then reranking narrows to a small evidence packet.

Rationale: the screenshots show that narrow lexical retrieval can miss the right evidence. Broad retrieval alone would increase noise, so strict reranking is the balancing stage.

Alternative considered: simply increasing `limit`. That increases the chance of the right source appearing but also feeds more junk to the answer layer.

### Decision: Treat hash embeddings as fallback, not quality semantic retrieval

The hash embedding backend can remain useful for tests and offline fallback, but RAG v2 diagnostics should distinguish it from real semantic embeddings. If hash embeddings are used, the retrieval mode should report that semantic quality is degraded.

Rationale: calling hash embeddings "semantic" hides a major quality risk in deployment.

Alternative considered: removing hash embeddings. That would make tests and minimal local installs heavier. Keeping them with clearer diagnostics gives both portability and honesty.

### Decision: Add retrieval-ready chunk metadata during indexing

RAG v2 needs more than page number and first-line section label. Chunk metadata should include rebuildable fields such as:

- heading path or inferred section path
- normalized aliases found in the chunk
- entity and scope tags found in headings versus body text
- section kind and retrieval flags
- evidence cues such as definition, system text, cost, dice pool, duration, prerequisite, targeting, advancement, consequence, example, lore, table of contents, index, or character sheet

Rationale: reranking can then prefer system text for a targeting question and advancement rules for a "how do I learn" question.

Alternative considered: deriving all cues at query time. That avoids migration but repeats work and makes diagnostics less stable.

### Decision: Evidence gate should reject mere mentions

The evidence gate should compare the query plan's required evidence to selected chunks. For example:

- advancement intent requires advancement/acquisition evidence, not just a discipline mention
- targeting intent requires system or target/applicability evidence
- definition intent requires definition or explanatory evidence
- cost intent requires cost or prerequisite evidence

If selected chunks do not satisfy the evidence need, retrieval should return `insufficient` with best-known nearby sources rather than `answerable`.

Rationale: this is the difference between "I found Obfuscate on a character sheet" and "I found the rule for learning Obfuscate."

### Decision: Keep core/supplement precedence after reranking

RAG v2 must preserve existing source authority behavior. Supplement-specific authority can outrank core for scoped questions, but comparable supplement conflicts must still surface as ambiguity.

Rationale: better retrieval must not silently erase existing rules precedence safeguards.

## Risks / Trade-offs

- More metadata may require rebuilding existing rules indexes -> provide audit diagnostics and a refresh path rather than failing silently.
- Reranking may over-filter and produce more refusals at first -> stage-aware diagnostics will show whether evidence was too strict.
- Candidate generation may become slower -> keep candidate caps and expose timing diagnostics.
- Evidence labels may be imperfect -> make labels rebuildable and test-driven, and preserve raw chunks for inspection.
- Compatibility with existing JSON consumers may break if fields are removed -> add new fields and preserve existing `primary_results` and `fallback_results` during the transition.

## Migration Plan

1. Add RAG v2 metadata fields and rebuild logic while preserving the current schema fields.
2. Add audit/reporting for stores that lack RAG v2 metadata.
3. Implement candidate generation and reranking behind a versioned retrieval mode.
4. Emit evidence packets while still returning current primary/fallback results.
5. Switch bot source selection to evidence packets once regression cases pass.

Rollback can use the existing exact/hybrid retrieval mode if RAG v2 diagnostics show unacceptable degradation.

## Open Questions

- None requiring user input. The architecture call is to implement a local deterministic reranker first, with optional learned reranking plugged in by the later hosting change.
