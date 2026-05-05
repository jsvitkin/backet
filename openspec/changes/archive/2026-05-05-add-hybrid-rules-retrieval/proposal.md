## Why

Rules queries currently retrieve raw chunks with source metadata using exact full-text matching only. That passes precise rule lookups, but authoring prompts often use natural language such as "poor Soviet housing projects" or "create a new domain," where the useful rule text uses different terms like Chasse, public housing, banlieues, or downscale hunting grounds.

This change adds local semantic retrieval to the rules corpus while preserving exact search, source attribution, book precedence, and ambiguity handling. It also aligns the workflow skills with the full source process: vault canon first, rules corpus second, and external research only when the question needs real-world facts outside the local corpus.

## What Changes

- Add local embeddings for ingested rule chunks and store them under the durable `.backet/rules/` rules store.
- Make `backet rules query` use hybrid retrieval: exact FTS/BM25 plus semantic vector candidates, filtered and reranked with metadata, book precedence, and extraction quality.
- Preserve raw source chunk output, source metadata, core-versus-supplement precedence, and explicit ambiguity errors.
- Add deterministic query metadata indicating whether semantic retrieval was available, used, or skipped.
- Add a dedicated `backet rules index` command that builds or refreshes rule embeddings and reports semantic index coverage.
- Update workflow skill guidance so authoring tasks explicitly triage source needs across:
  - local vault canon via `backet context`
  - ingested rules via `backet rules query`
  - external research with citations when the needed information is not in vault canon or rules
- Keep Backet's CLI responsible for local retrieval only; web research remains an agent action guided by skills, not a new Backet network-search feature.

### Non-Goals

- Do not replace exact rules retrieval with vector-only retrieval.
- Do not add remote embedding APIs or send rulebook contents to remote services.
- Do not copy source PDFs into the vault.
- Do not build a normalized mechanics/rule-card database.
- Do not add a Backet CLI web-search command.
- Do not make workflow skills store canon or rules knowledge internally.

## Capabilities

### New Capabilities

- `hybrid-rules-retrieval`: Local rule chunk embeddings, hybrid rules query ranking, semantic fallback/status, and quality-aware reranking.
- `workflow-source-triage`: Skill-facing workflow guidance for separating vault canon, rules guidance, external research, and unresolved choices before drafting canon.

### Modified Capabilities

- None.

## Impact

- CLI: affects `backet rules ingest`, `backet rules query`, `backet rules audit`, and adds a dedicated `backet rules index` refresh/status command.
- Per-vault state: adds durable rule embedding metadata under `.backet/rules/`; source PDFs remain external; scratch/cache artifacts remain rebuildable and ignored.
- Retrieval behavior: improves recall for conceptual authoring prompts while keeping bounded raw chunks and source metadata.
- Skill pack: updates `workflow-authoring` and likely `city-foundation` guidance to present `Canon says`, `Rules suggest`, `External research`, and `Open choices` as separate lanes.
- Dependencies: reuses the existing local embedding backend abstraction where possible; Sentence Transformers remains local, with deterministic fallback behavior when unavailable.
- Tests/docs: adds rules retrieval regression tests, rules semantic index coverage tests, workflow skill asset tests, and README guidance for the multi-source workflow.
