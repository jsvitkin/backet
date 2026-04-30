## Context

`backet index` currently scans every Markdown file below the vault root except `.backet/`, then stores note metadata, heading-aware chunks, full-text search data, and local embeddings in `.backet/state/vault-index.sqlite3`. That is correct for small fixture vaults, but mature Obsidian vaults often include plugin folders, templates, archive areas, generated exports, daily notes, or workbench files that are Markdown but not campaign canon.

The product boundary remains:

```text
repository/
  src/backet/          # CLI implementation
  skills/              # Codex skill pack, distributed separately from vaults
  openspec/            # product/change docs

target vault/
  .backetignore        # committed, user-editable index policy
  .backet/
    .gitignore         # Git policy for Backet-owned state only
    state/             # committed durable index DB
    memory/            # committed derived readable memory
    rules/             # committed ingested rules corpus
    cache/             # ignored rebuildable scratch
    temp/              # ignored rebuildable scratch
    ocr-work/          # ignored rebuildable scratch
  .obsidian/           # ignored by default for indexing
  campaign notes...    # human-authored canon
```

Skills should not learn filesystem ignore semantics. They continue to request bounded context through the CLI, and the CLI decides what belongs in the indexed canon corpus.

## Goals / Non-Goals

**Goals:**

- Add a visible, user-editable root `.backetignore` policy for vault Markdown indexing.
- Generate default policy content on `backet init` and safely restore it with `backet doctor --fix` when missing.
- Apply the policy before parsing, fingerprinting, chunking, embedding, or storing Markdown notes.
- Remove previously indexed rows when a path becomes ignored, so retrieval cannot surface excluded notes.
- Keep human-friendly terminal output and deterministic `--json` output clear about the ignore policy path and indexed note count.
- Preserve the separation between canonical vault notes, derived index/memory state, and the ingested rules corpus.

**Non-Goals:**

- No new authoring workflow or skill-pack behavior is required.
- No broad CLI matrix of exclude/include flags in this slice.
- No automatic migration of vault folder structures, frontmatter, links, or note content.
- No change to PDF rulebook ingestion, OCR repair, rule precedence, or rules query behavior.
- No requirement that existing vaults follow the Prague numbered folder taxonomy.

## Decisions

### 1. Use root `.backetignore` for index policy

The index ignore file should live at the vault root:

```text
target vault/.backetignore
```

Why:

- It mirrors `.gitignore`, making the policy visible and familiar.
- It belongs to the user's vault information architecture, not to opaque generated state.
- It can be committed and reviewed alongside vault structure changes.

Alternative considered:

- `.backet/index.ignore`. Rejected because it is harder for users to discover and blurs user-editable policy with generated Backet state.

### 2. Keep `.backetignore` separate from `.backet/.gitignore`

`.backetignore` controls what Backet indexes as vault canon. `.backet/.gitignore` controls what Git ignores inside Backet-owned state.

```text
.backetignore
  affects: index scanner, stale detection, context, memory

.backet/.gitignore
  affects: Git status for cache/, temp/, ocr-work/
```

Why:

- Index policy and Git policy answer different questions.
- Users may want a note excluded from retrieval while still committed, or committed generated state while still ignored from indexing.

Alternative considered:

- Reusing root `.gitignore`. Rejected because users may commit files that should not be indexed, and some ignored files may still be relevant in other workflows.

### 3. Use gitignore-style matching, preferably via `pathspec`

The implementation should use gitignore-style pattern semantics for `.backetignore`, with comments, blank lines, directory patterns, globs, `**`, and negation.

Default content should be conservative:

```gitignore
# Backet index ignore
# Patterns are relative to the vault root and use gitignore-style syntax.

.backet/
.obsidian/
.git/
.trash/
Templates/
Archive/
Daily Notes/
```

Why:

- Users already understand this grammar.
- A proven parser reduces edge cases around directory matching and negation.
- A default file documents the behavior directly in the vault.

Alternative considered:

- A custom newline-only prefix matcher. Rejected because it would be deceptively simple and likely diverge from user expectations.

### 4. Keep built-in safety exclusions

The scanner should always exclude `.backet/` even if `.backetignore` is missing or edited to unignore it. It should also avoid traversing obvious VCS/system directories such as `.git/` for performance and safety, while the generated file still lists them for clarity.

Why:

- Indexing generated Backet state would pollute retrieval with derived memory and internal files.
- A user typo in `.backetignore` should not create recursive or self-referential retrieval behavior.

Alternative considered:

- Treat `.backetignore` as fully authoritative. Rejected because Backet-owned state has stronger product invariants than ordinary vault folders.

### 5. Missing ignore files should not block indexing

If `.backetignore` is absent, indexing should continue with built-in safety exclusions and deterministic output should report the expected policy path. `backet doctor` should surface the missing file as a safe-to-fix warning, and `backet doctor --fix` should create the default file only when it does not already exist.

Why:

- Older initialized vaults should not break.
- Users should not lose retrieval just because the policy file was deleted.
- Safe repair remains additive and does not overwrite user policy.

Alternative considered:

- Hard-failing when `.backetignore` is absent. Rejected because it would make the new feature a compatibility hazard.

### 6. Ignored paths are treated as absent from the corpus

The scanner should compute current Markdown notes after applying `.backetignore`. Any previously indexed note that is now ignored should appear as deleted during staleness inspection and should be removed during the next index refresh.

Why:

- Retrieval must not surface content after the user excludes it.
- This matches the mental model of an ignore file: ignored files do not exist to the indexing corpus.

Alternative considered:

- Keeping ignored rows but filtering only at query time. Rejected because it risks leaks through memory building, stale state, or future retrieval surfaces.

### 7. Bounded retrieval remains unchanged above the scanner

Hybrid retrieval continues to operate over the index using exact search, semantic scores, metadata filters, and hierarchy-aware ranking. The ignore file changes corpus membership before retrieval begins; it does not create a new retrieval scope or allow whole-vault loading.

```text
Markdown files
   │
   ├─ built-in safety exclusions
   ├─ .backetignore policy
   ▼
indexed canon corpus
   │
   ├─ exact FTS
   ├─ local vectors
   ├─ path/title metadata
   └─ hierarchy-aware ranking
   ▼
bounded context bundles
```

Why:

- The retrieval layer stays small and predictable.
- Skills keep receiving bounded source metadata without needing new behavior.

Alternative considered:

- Adding ignore-aware options to `backet context`. Rejected because query-time options would duplicate scanner policy and make agent behavior less deterministic.

### 8. Keep v1 JSON output compact

`backet index --json` should include the index ignore policy path and the usual indexed note counts, but it should not add `ignored_markdown_count` or sample ignored paths in v1.

Why:

- The index command's primary contract remains the effective indexed corpus.
- Avoiding ignored path samples keeps agent-facing output compact and stable.
- Users can inspect `.backetignore` directly when they need to understand policy.

Alternative considered:

- Reporting ignored counts and sample ignored paths. Rejected for v1 because it adds output surface area before there is a clear debugging need.

## Risks / Trade-offs

- [A user accidentally ignores important canon] -> JSON and human output should expose the policy path and indexed counts; users can edit `.backetignore` and re-run `backet index --full`.
- [Pattern behavior surprises users] -> Use standard gitignore-style semantics and document that patterns are relative to the vault root.
- [New dependency increases packaging surface] -> Prefer a small pure-Python dependency such as `pathspec` and cover wheel build/install smoke behavior.
- [Existing vaults lack `.backetignore`] -> Continue indexing with built-in safety exclusions and make `doctor --fix` additive.
- [Ignored files remain in derived memory from previous builds] -> Since memory is derived from the current index, users should rebuild memory after index refresh; implementation tests should cover that ignored notes no longer feed memory after rebuild.
- [Negation can unignore files inside ignored directories] -> Rely on the chosen gitignore parser's documented behavior and add focused tests for basic negation if supported.

## Migration Plan

1. Introduce `.backetignore` path helpers and default template content.
2. Update `backet init` to create `.backetignore` for new vaults.
3. Update `backet doctor` and `doctor --fix` to report and restore missing `.backetignore` safely.
4. Update the index scanner to load the policy and filter Markdown candidates before fingerprinting or parsing.
5. Ensure ignored paths are removed from durable index state on normal and full reindex.
6. Update README usage notes to explain `.backetignore` versus `.backet/.gitignore`.

Rollback:

- If the parser or UX proves wrong before release, remove `.backetignore` generation and scanner filtering from the slice.
- For vaults that already received the file during development, leaving `.backetignore` in place is harmless because older Backet versions will ignore it.

## Open Questions

- None.
