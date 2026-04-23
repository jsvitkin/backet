## Context

The sample Prague-by-Night vault already has enough Markdown to make naive prompt loading impractical, and later campaign growth will amplify that problem. The notes are mostly plain Markdown without frontmatter or wiki-link graph structure, so retrieval cannot assume a rich existing metadata layer; it must work from file paths, headings, content, and any derived memory `backet` creates.

This change is the first retrieval substrate for vault canon only. It deliberately excludes rulebook PDFs so the vault retrieval model can stabilize before a second corpus is added.

## Goals / Non-Goals

**Goals:**

- Index Markdown vault content into committed per-vault state.
- Detect stale state after external vault edits.
- Assemble bounded context bundles using hybrid retrieval.
- Persist rebuildable readable memory capsules under `.backet/`.

**Non-Goals:**

- Ingest or query external rulebook PDFs.
- Build workflow-specific authoring commands.
- Define a universal future taxonomy for every possible scope label.

## Decisions

### 1. Use a portable SQLite-backed per-vault index as the primary durable store

The primary vault index will live under `.backet/` in a portable SQLite-backed store that can hold note metadata, chunks, full-text search data, embedding references, and retrieval bookkeeping.

Why:

- SQLite fits the local CLI model and can travel with the vault.
- It supports committed durable state better than a separate long-running service.
- It keeps indexing, retrieval, and rebuild flows simple for a single-vault workflow.

Alternative considered:

- External vector database service. Rejected for foundation work because it adds operational weight and weakens portability.

### 2. Treat Markdown parsing and chunking as path-aware and heading-aware

Vault indexing will derive structure from file paths, heading hierarchy, and content chunks rather than depending on frontmatter or wiki-links.

Why:

- The current example vault has stable folder taxonomy and headings, but little machine-readable metadata.
- This captures real authoring structure without forcing an immediate vault rewrite.

Alternative considered:

- Requiring frontmatter-first indexing from day one. Rejected because it would distort the current authoring workflow too early.

### 3. Use hybrid retrieval for bundle assembly

Context assembly will blend:

- exact lookup for titles, names, and known terms
- semantic retrieval for thematic or conceptual queries
- metadata filters for source scope
- hierarchy-aware expansion to pull nearby canon when needed

Why:

- Vector-only retrieval is too fuzzy for exact campaign canon.
- Exact-only retrieval is too brittle for exploratory or thematic queries.

Alternative considered:

- Pure vector search. Rejected because it does not respect exact canon lookups well enough.

### 3a. Use Sentence Transformers with `multi-qa-MiniLM-L6-cos-v1` as the default local embedding backend

The default local embedding backend for vault retrieval will be Sentence Transformers using `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`.

Why:

- Sentence Transformers is a mature local embedding stack with strong semantic-search support.
- The `multi-qa` MiniLM family is trained specifically for question-to-passage retrieval, which matches `backet context` usage better than a general similarity-only baseline.
- The model is lightweight enough for local use while exact lookup still covers proper nouns and path-sensitive canon queries.

Alternative considered:

- `sentence-transformers/all-MiniLM-L6-v2`. Rejected as the default because it is a good general-purpose model, but the `multi-qa` variant is a better fit for retrieval queries over passage chunks.
- Remote embedding APIs. Rejected because vault retrieval is explicitly local-only.

### 3b. Assume English-only vault content in v1

This proposal assumes English-language vault content and English-language retrieval queries in v1.

Why:

- The user expects vaults and rules to be in English.
- Multilingual retrieval is not a current requirement and should not complicate the first embedding choice.

Alternative considered:

- Designing for multilingual retrieval from day one. Rejected because it introduces complexity without a current product need.

### 4. Expose a small set of retrieval-oriented commands

This change assumes a compact command surface such as:

```text
backet index
backet context ...
backet memory ...
```

Why:

- Small verbs are easier for both humans and skills to rely on.
- It keeps retrieval as an operational layer beneath later authoring skills.

Alternative considered:

- Large numbers of note-type-specific CLI commands at the retrieval layer. Rejected because those belong to later workflow changes.

### 4a. Keep first-class scope labels narrow in v1

The first-class context scopes in v1 will be:

- `vault`
- `note`
- `path`
- `subtree`

Everything else, including plotlines, districts, factions, NPCs, organizations, and locations, will be inferred through path-aware retrieval, titles, or later workflow-specific commands.

Why:

- It gives us stable primitives without hardcoding the future authoring taxonomy too early.
- `vault`, `note`, `path`, and `subtree` are generic enough to survive future information-architecture changes.
- Plotlines can still be retrieved through path-aware ranking without becoming a dedicated retrieval command at this layer.

Alternative considered:

- Exposing many domain-specific scopes from day one. Rejected because the workflow layer has not been designed yet.

### 5. Persist readable memory capsules alongside machine index state

Derived memory will be stored under `.backet/memory/` as readable Markdown capsules keyed to useful scopes, while the index database carries denser machine state.

Likely early capsule families:

```text
.backet/memory/
  city/
  districts/
  factions/
  institutions/
  plotlines/
```

Why:

- Human-readable memory gives users and agents a stable summary surface.
- It keeps the retrieval model from depending entirely on opaque DB state.

Alternative considered:

- Opaque DB-only memory. Rejected because it is harder to inspect, diff, and regenerate intentionally.

### 5a. Keep vault retrieval durable state in one committed DB plus readable memory files

The durable vault retrieval state will live primarily in a single committed SQLite database, with readable memory capsules stored as separate Markdown files under `.backet/memory/`.

The single DB will hold:

- note metadata
- path and heading structure
- chunk records
- full-text search data
- embeddings
- staleness fingerprints
- retrieval bookkeeping

Why:

- One durable DB keeps indexing atomic and reduces coordination complexity.
- The sample vault size is easily within SQLite's comfort zone.
- Separate readable memory files preserve inspectability without fragmenting the core index into multiple committed stores.

Alternative considered:

- Splitting vault retrieval into several committed DBs or manifests. Rejected because it adds complexity before there is enough scale pressure to justify it.

### 6. Detect stale state with content-based refresh triggers

Indexing should compare stored source fingerprints against the canonical note corpus so that changes made outside `backet` are still recognized.

Why:

- Obsidian editing and Git workflows mean external edits are normal, not exceptional.
- The user explicitly wants that case handled.

Alternative considered:

- Assuming all content changes happen through `backet`. Rejected because it is false for the actual workflow.

### 7. Validate retrieval with layered fixture-based tests

This change will require:

- unit tests for chunking, ranking composition, and scope filtering
- integration tests against representative vault fixtures
- regression tests for committed index portability and deterministic machine-readable context output

Why:

- Retrieval bugs are often ranking or boundary bugs that unit tests alone will miss.
- The committed per-vault index model needs explicit portability coverage.

Alternative considered:

- Relying primarily on manual vault experimentation. Rejected because retrieval regressions are subtle and easy to miss without fixtures.

## Risks / Trade-offs

- [Committed index DBs may create noisy diffs] -> Keep the durable schema compact and isolate scratch artifacts behind `.backet/.gitignore`.
- [Semantic retrieval may overfit to prose similarity] -> Keep exact lookup and source metadata first-class in bundle ranking.
- [Plain Markdown without rich metadata weakens scope inference] -> Start with path and heading structure, then layer memory capsules to improve retrieval over time.
- [Local embeddings can be slower on weaker machines] -> Support explicit indexing commands and incremental refresh rather than hiding all work behind implicit background jobs.
- [Retrieval quality can regress invisibly as ranking logic evolves] -> Keep fixture-based regression coverage for canonical lookups and bounded-context assembly.

## Migration Plan

1. Define the durable per-vault index schema and `.backet/` layout additions.
2. Implement Markdown parsing, chunking, and local embedding generation.
3. Implement stale-state detection and refresh behavior.
4. Implement `backet context` and `backet memory` flows on top of the index.

Rollback would mainly involve revising the index schema or memory layout before workflow-specific features depend on them.

## Open Questions

- None at this layer.
