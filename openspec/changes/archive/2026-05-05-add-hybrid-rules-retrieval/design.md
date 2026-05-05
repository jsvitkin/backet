## Context

`backet` currently has two separate retrieval surfaces:

- vault context retrieval, which already stores note chunk embeddings and combines exact and semantic ranking
- rules retrieval, which stores rule chunks and FTS rows, then ranks with SQLite FTS5/BM25 plus book precedence

The rules implementation is intentionally conservative: it returns raw source chunks with metadata and does not normalize mechanics. That behavior should remain. The missing piece is recall for natural authoring prompts. A user asking to create "a poor Ravnos domain in south Prague near Soviet housing projects" is not making one rule lookup; they are asking for several source lanes:

- vault canon: what the Prague chronicle already says
- rules: domain traits, hunting grounds, clan or loresheet relevance
- external research: real Prague geography and housing-estate context

Only the first two lanes belong in the Backet CLI. The skill layer should tell agents when and how to use external research, but Backet should not become a web-search tool in this change.

## Goals / Non-Goals

**Goals:**

- Add local semantic embeddings for ingested rule chunks.
- Make rules queries retrieve candidates from both exact FTS and semantic vector similarity.
- Keep exact rule terms, source metadata, book precedence, and ambiguity behavior authoritative.
- Penalize low-confidence OCR, tiny chunks, and common non-answer sections such as table of contents, index, sheets, and art-heavy pages during ranking.
- Report semantic index availability and coverage in deterministic command output.
- Update workflow skills so they explicitly triage source needs across canon, rules, and external research before drafting.

**Non-Goals:**

- No vector-only rules retrieval.
- No remote embedding or hosted vector database dependency.
- No web search inside the Backet CLI.
- No normalized rule-card or mechanics database.
- No full workflow-specific "brief" command in this slice.
- No automatic rewriting of existing vault notes or rule corpus contents.

## Decisions

### 1. Store rule embeddings beside the rules corpus, not in the vault index

Rule embeddings should live in `.backet/rules/`, separate from the vault Markdown index.

Likely schema:

```text
rules.sqlite3
  rule_chunks
  rule_chunks_fts
  rule_chunk_embeddings
    chunk_id
    backend
    model
    dimensions
    content_hash
    embedding_json
    embedded_at
  rule_chunk_retrieval_metadata
    chunk_id
    content_hash
    section_kind
    retrieval_flags_json
    updated_at
```

Why:

- The rules corpus has a different lifecycle, provenance model, and audit surface than vault canon.
- Re-ingesting or repairing rule pages should not touch vault note embeddings.
- Embedding rows can be rebuilt when the local model changes without mutating raw chunks.
- Retrieval metadata can be rebuilt from chunk content and source metadata without changing the raw extracted text.

Alternative considered:

- Store embeddings directly on `rule_chunks`. Rejected because model migration and partial rebuilds would churn the core source table.
- Store rules in the main vault index DB. Rejected because earlier rules-ingestion design intentionally separated these corpora.
- Store retrieval-quality flags only in query code. Rejected because stable derived metadata is easier to audit, test, and reuse across exact and semantic ranking.

### 1a. Store embeddings as JSON for v1

Rule embeddings should use a text `embedding_json` field in v1.

Why:

- It matches the current vault index approach, making implementation and tests simpler.
- It keeps the committed rules store inspectable with ordinary SQLite tooling.
- Storage size is not a primary constraint for the expected vault workflow.
- A future compact encoding can be introduced with a targeted migration if DB churn or performance becomes a concrete problem.

Alternative considered:

- Store vectors as compact binary blobs. Rejected for v1 because the extra serialization surface does not buy enough value while storage space is not the limiting factor.

### 2. Reuse the existing local embedding abstraction

Rules should use the same `backet.embeddings` backend abstraction as vault context retrieval.

Default behavior:

- `BACKET_EMBEDDING_BACKEND=sentence-transformers` requires Sentence Transformers and fails clearly if unavailable.
- `BACKET_EMBEDDING_BACKEND=auto` may fall back to the hash backend, but JSON output must identify the backend actually used.
- The system must never send rulebook text to a remote embedding service.

Why:

- The local-only rule from ingestion remains intact.
- Users get one backend configuration model for vault and rules.
- Fixture tests can use the deterministic hash backend while real installations can use Sentence Transformers.

Alternative considered:

- Add a rules-specific embedding dependency. Rejected because it duplicates configuration and testing.

### 3. Keep FTS first-class and add semantic candidates as recall

`backet rules query` should gather candidates from both:

- FTS/BM25 over `rule_chunks_fts`
- vector similarity over `rule_chunk_embeddings`

Then merge by `chunk_id` and rerank using weighted reasons:

```text
score =
  exact score
  + semantic score
  + metadata/scope boosts
  + precedence boosts
  - quality penalties
  - non-answer-section penalties
```

The response should include match reasons such as `exact`, `semantic`, `scope-tag`, `core-fallback`, `supplement-precedence`, or `quality-penalty`.

Why:

- Exact terms such as Chasse, Portillon, Rouse Check, Ravnos, and Blood Potency need lexical precision.
- Conceptual prompts need semantic recall when the user does not know the rulebook vocabulary.
- Returning reasons keeps agent-facing output inspectable.

Alternative considered:

- Pure vector search. Rejected because it is too fuzzy for authoritative rules.
- FTS-only with query expansion. Rejected because it requires hand-maintained synonym maps and still misses broad conceptual language.

### 4. Preserve precedence and ambiguity after candidate gathering

The existing rule hierarchy remains:

- supplement-specific sources outrank core when a relevant `scope_tag` applies
- core remains available as fallback context
- multiple comparable supplement-specific matches surface ambiguity instead of being silently resolved

Hybrid retrieval changes candidate discovery and ranking, not authority.

Why:

- Similarity cannot decide source authority.
- Rules retrieval must stay honest when the corpus contains multiple potentially conflicting specific books.

Alternative considered:

- Let semantic score choose between books. Rejected because a semantically close chunk from the wrong source can be mechanically misleading.

### 5. Store lightweight retrieval-quality metadata and use it during ranking

Rules ingestion, repair, and indexing should derive lightweight retrieval metadata for each chunk, then query ranking should use that metadata. This metadata should be rebuildable and should not replace the raw chunk.

Examples:

- `section_kind`: `rules`, `lore`, `toc`, `index`, `sheet`, `art`, `unknown`
- `retrieval_flags_json`: `["suspect_ocr", "very_short", "navigational"]`

Rules ranking should account for both existing ingestion quality metadata and these derived retrieval flags:

- lower confidence OCR pages should rank lower unless exact/semantic evidence is strong
- suspect pages and very short chunks should rank lower
- table of contents, index, character sheet, form, and art-heavy chunks should rank lower for ordinary rules queries

Why:

- The current Core Rulebook audit shows useful pages and noisy OCR/art pages in the same corpus.
- Ranking should prefer explainable rule text over navigational or low-confidence artifacts.
- Storing the classification once makes query behavior more stable, makes tests clearer, and lets audit/status explain why a chunk was downranked.

Alternative considered:

- Filter noisy chunks out entirely. Rejected because some OCR chunks are useful, and audit/repair workflows need the data to remain inspectable.
- Compute all non-answer penalties only at query time. Rejected because it hides the classification from audit/status output and duplicates heuristics across query paths.

### 6. Add a dedicated `backet rules index` command

Ingestion should be able to build embeddings when the backend is available, but users should also be able to ingest rulebooks without Sentence Transformers installed.

The first implementation should add a dedicated operational command:

```text
backet rules index <vault> [--book-id <id>] [--full]
```

The command should:

- embedding backend and model
- number of chunks with embeddings
- number of stale embeddings where `content_hash` differs
- number of chunks with retrieval-quality metadata
- missing/stale counts
- rebuild status for embeddings and derived retrieval metadata

`rules audit` should remain focused on extraction quality, but it may point to `backet rules index` when semantic coverage is missing or stale. `rules query` should still report whether it ran `hybrid`, `exact_only`, or `semantic_unavailable`.

Why:

- Large PDFs should remain ingestible on a minimal installation.
- Agents need deterministic signals when semantic retrieval was not actually used.
- Indexing is retrieval infrastructure, not extraction-quality audit; a dedicated command mirrors the existing `backet index` mental model for vault notes.
- A separate command gives users a clear way to refresh embeddings after installing Sentence Transformers or changing embedding backend settings.

Alternative considered:

- Make embeddings mandatory for `rules ingest`. Rejected because it would make OCR/PDF ingestion depend on optional ML packages and slow the first successful ingest.
- Fold semantic status and repair into `rules audit`. Rejected because audit already means "is the extracted source text suspect?", while semantic indexing means "is retrieval infrastructure built and fresh?"

### 7. Update skills for source-lane triage, not web automation

`workflow-authoring` should teach agents to separate source needs before drafting:

```text
Canon says
Rules suggest
External research
Open choices
```

For a domain prompt, the skill should first use `backet context` for local canon and `backet rules query` for rules. If the prompt asks for real-world facts not present in local sources, the skill should use the agent's normal web research tools with citations and clearly mark those facts as external support.

Why:

- Skills are the authoring layer and should tell agents how to arbitrate sources.
- Backet should remain a local retrieval CLI, not a network research product.
- Vault canon must remain authoritative over both rule suggestions and web facts.

Alternative considered:

- Add a Backet `web search` command. Rejected because it would complicate the CLI boundary, introduce network policy questions, and duplicate agent capabilities.

### 8. Keep releases split between CLI and skills

The CLI implementation and skill-pack guidance can ship independently through the existing update mechanisms:

- `backet update apply` updates the CLI package and schema/query behavior.
- `backet skills update` updates installed workflow instructions.

The proposal should update both repo assets, but users may need both update paths before the whole experience is active.

Why:

- The project already treats CLI and skills as separate releasable surfaces.
- Retrieval improvements can function without skill updates, but workflow behavior will not fully reflect the new multi-source process until the skills are refreshed.

Alternative considered:

- Bundle skill updates into CLI update. Rejected because existing product boundaries keep them separate.

## Risks / Trade-offs

- [Semantic search returns plausible but wrong rule chunks] -> Keep exact search, source metadata, and precedence first-class, and expose match reasons.
- [Optional embedding backend creates inconsistent user experience] -> Report backend/model and retrieval mode in JSON output and `rules index` status.
- [Embedding a large rules corpus is slow] -> Support incremental rebuilds keyed by `content_hash`, and keep ingestion usable before embeddings are complete.
- [Committed embedding vectors make large diffs] -> Store JSON for inspectability, avoid rewriting unchanged embeddings, and migrate to compact blobs only if real DB churn becomes a problem.
- [Rules query output changes break agents] -> Preserve existing `primary_results` and `fallback_results` shape where possible; add metadata rather than removing fields.
- [Skills overreach into web research] -> Keep skill language focused on source triage, citations, and canonical precedence; do not encode browsing implementation details.

## Migration Plan

1. Add a schema migration that creates the rule embedding metadata table while preserving existing `rules.sqlite3` contents.
2. Add embedding generation for new or changed chunks during ingest/repair and a rebuild path for existing rule stores.
3. Update `rules query` to merge exact and semantic candidates, then apply quality-aware ranking and existing precedence.
4. Add `backet rules index` output for semantic coverage, stale embeddings, and derived retrieval metadata coverage.
5. Update workflow skill assets and tests.
6. Update README guidance for optional Sentence Transformers and multi-source authoring.

Rollback:

- Keep FTS tables and raw rule chunks untouched.
- If semantic retrieval fails, fall back to exact-only behavior and report that semantic retrieval is unavailable.
- If schema migration needs rollback during development, drop only the embedding table; raw corpus remains intact.

## Open Questions

- None for the first implementation slice.
