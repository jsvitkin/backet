## Context

`backet rules ingest` currently asks the user for book-level metadata, including repeatable `--scope-tag` values. Those tags are copied to every chunk from the book and then used by rules retrieval for filtering, supplement precedence, and ambiguity handling.

That worked as a small first slice, but Vampire rulebooks are increasingly mixed. A book such as Camarilla is source-level Camarilla material while also containing Banu Haqim rules, rituals, loresheets, institutional-conflict mechanics, and Camarilla-perspective commentary on enemy sects. A single book-level tag cannot distinguish "this is authoritative mechanics for this topic" from "this book mentions this topic from an in-world perspective."

The CLI should remain the operational owner of ingestion. Skills may consume richer rules metadata later, but the normal user flow should stay `backet rules ingest <vault> <pdf> ...`; users should not need to run a separate Codex skill for every book.

Durable ingested rules state belongs under the target vault's `.backet/rules/` area. Source PDFs remain external. Generated scope assertions are derived state, but they are important enough to commit with the rules corpus because they affect retrieval correctness and should travel with the vault backup.

## Goals / Non-Goals

**Goals:**

- Automatically generate page, section, and chunk scope assertions during rules ingestion.
- Remove manual `--scope-tag` input from `backet rules ingest`; ingestion should infer source and span scopes automatically.
- Store assertions with tag, span, role, confidence, generator version, and evidence.
- Apply high-confidence assertions to chunks so rules queries can filter, boost, and report scope at chunk level.
- Expose a review/audit workflow for uncertain assertions without requiring source PDF copies inside the vault.
- Keep deterministic JSON output complete for agents and human output concise.
- Keep retrieval bounded to indexed rules chunks and metadata rather than loading whole rulebooks into context.

**Non-Goals:**

- No remote model calls or hosted AI classification of private rulebook text.
- No full canonical mechanics database or normalized rule graph.
- No requirement that users manually pre-tag pages before ingestion.
- No Obsidian note creation from rulebook text.
- No skill-pack release dependency for the core ingestion behavior.

## Decisions

### 1. Model scope as assertions, not only tags

Add a durable scope assertion model with at least:

- `book_id`
- page or chunk span
- normalized typed tags such as `sect:camarilla`, `clan:banu-haqim`, `discipline:blood-sorcery`, `mechanic:institutional-conflict`, `content:loresheet`
- role such as `source`, `mechanical-authority`, `setting-authority`, `perspective`, or `mention`
- confidence
- status such as `applied`, `suggested`, `rejected`, or `superseded`
- evidence JSON, including matched headings, outline entries, aliases, nearby markers, and generator name/version

Why:

- Retrieval authority depends on more than topic presence.
- A Camarilla-perspective Sabbat section should be findable, but it should not outrank a dedicated Sabbat source for Sabbat mechanics.
- Evidence makes automatic tagging inspectable and testable.

Alternative considered:

- Add more book-level `--scope-tag` values. Rejected because it over-applies all tags to every chunk and increases false precedence.

### 2. Keep normal ingestion automated and local

`backet rules ingest` should generate scope assertions after extraction/chunking and before final indexing/ranking metadata is considered complete. The generator should use local deterministic and heuristic inputs:

- PDF table of contents from PyMuPDF when available
- page headings and section labels already extracted during ingestion
- known vocabulary and aliases
- mechanics markers such as `Bane`, `Clan Compulsion`, `Disciplines`, `Rituals`, `Loresheet`, and named conflict systems
- local semantic embeddings only if already available locally; embeddings can assist candidate grouping but must not be required

Why:

- Users should not be responsible for clean taxonomies at ingest time.
- Private rulebook text must remain local.
- Deterministic heuristics give reliable tests and explainable evidence.

Alternative considered:

- Require a Codex skill to curate each ingested PDF. Rejected for the default workflow because it creates manual operational overhead and couples ingestion to the current agent session.

### 3. Use a controlled typed vocabulary with aliases

Introduce a local Vampire: The Masquerade rules scope taxonomy resource shipped with the CLI. The seed list should cover VTM/WoD vampire terminology broadly enough for the user's Vampire corpus, while explicitly excluding non-Vampire game lines such as Werewolf, Mage, Changeling, Wraith, and Hunter unless a VTM source needs a cross-reference. It should contain canonical typed tags and aliases, for example:

```yaml
sect:camarilla:
  aliases: ["camarilla", "ivory tower"]
clan:banu-haqim:
  aliases: ["banu haqim", "children of haqim", "assamite", "assamites"]
discipline:blood-sorcery:
  aliases: ["blood sorcery", "quietus"]
content:loresheet:
  aliases: ["loresheet", "lore sheet"]
```

Why:

- Flat strings become ambiguous quickly.
- Typed tags let retrieval distinguish clan, sect, mechanic, content type, discipline, and topic.
- The taxonomy can grow incrementally without changing source PDFs or vault notes.
- Staying VTM-only keeps the first classifier useful without pretending to model all World of Darkness games.

Alternative considered:

- Free-form tags only. Rejected because free-form tags make automation and precedence inconsistent across books.

### 4. Use SQLite as the canonical assertion store and export manifests on demand

New assertion data should live in dedicated rules-store tables. SQLite remains the canonical persisted source under `.backet/rules/`; YAML manifests are generated by export/review commands and are applied back into SQLite after validation. The system should not write default `.backet/rules/scopes/<book_id>.yml` files during every ingest.

Existing book-level `scope_tags_json` should remain readable only as migration/fallback data for rulebooks ingested before this change. New ingestion should not require or accept manual source tags.

Candidate tables:

- `rule_scope_assertions`: durable generated/reviewed assertions
- `rule_chunk_scope_assertions`: applied chunk/assertion mapping, if direct many-to-many mapping is easier than recomputing spans

The export-on-demand manifest can mirror the DB for review:

```yaml
book_id: camarilla-v5
source_scope:
  - sect:camarilla
scopes:
  - pages: 159-168
    tags: [clan:banu-haqim, discipline:blood-sorcery, mechanic:ritual]
    role: mechanical-authority
    confidence: 0.95
    status: applied
    evidence:
      - toc_heading: Banu Haqim
      - page_heading: Disciplines
      - matched_terms: [Bane, Clan Compulsion, Rituals]
```

Why:

- SQLite remains the query source of truth.
- Export-on-demand gives the user and future agents an inspectable artifact without creating a stale second source of truth.
- Existing stored scope tags can still migrate old ingests without keeping the confusing ingest option.

Alternative considered:

- Write default YAML manifests during every ingest. Rejected because it creates dual canonical state and invites drift between SQLite and YAML.
- Replace book-level `scope_tags_json` immediately. Rejected because it would make migration riskier for existing rules databases.

### 4a. Use conservative confidence bands

The classifier should own confidence thresholds; users should not be expected to know them. The initial bands should be:

- `>= 0.85`: auto-apply to affected chunks
- `>= 0.60` and `< 0.85`: store as `suggested` and surface for review
- `< 0.60`: store only when useful for diagnostics, and never use for precedence

Unknown tags should not be used for authoritative precedence until normalized or reviewed, even if confidence is high.

Why:

- False authority is worse than a missed boost.
- The thresholds are simple enough to test and tune with fixtures.

Alternative considered:

- Ask users to provide thresholds or pick them per book. Rejected because confidence calibration is implementation responsibility, not user workflow.

### 5. Retrieval should use assertion role and confidence

Rules query candidate gathering should use chunk-level applied assertions for scope filters and boosts. Migrated source-level hints can remain a fallback when no chunk assertion exists for old ingests.

Ranking behavior:

- `mechanical-authority` and `setting-authority` can satisfy scope-specific supplement precedence.
- `perspective` and `mention` can help recall but should not establish authority over a dedicated source.
- high-confidence applied assertions add a scope match reason and boost
- suggested or low-confidence assertions may be reported in diagnostics but should not silently decide precedence

Why:

- Source authority cannot be inferred from semantic similarity alone.
- Fine-grained assertions reduce both false positives and false ambiguity errors.

Alternative considered:

- Keep all scope behavior in full-text search columns. Rejected because role, confidence, and evidence need structured access.

### 6. Review commands belong in the CLI, skills stay optional

Add or extend CLI surfaces such as:

- `backet rules scope audit <vault> --book-id <id>`
- `backet rules scope export <vault> --book-id <id>`
- `backet rules scope apply <vault> <manifest>`

These commands should be deterministic and usable by agents. A future skill can help review a manifest conversationally, but the CLI owns persistence and validation.

Why:

- CLI updates and skill updates can ship independently.
- Agents should not write directly into the rules database with private assumptions.
- Review workflows need stable machine-readable output.

Alternative considered:

- Store curation only in a Codex skill output file. Rejected because retrieval would not have a reliable operational contract.

## Risks / Trade-offs

- [Incorrect automatic tags] -> Store confidence and evidence, auto-apply only high-confidence assertions, and surface review-needed summaries.
- [Taxonomy grows too broad or inconsistent] -> Start with a small typed vocabulary and aliases, add tests for canonicalization, and allow unknown/untyped suggestions without using them for precedence.
- [False authority from mentions] -> Require assertion roles and prevent `mention`/`perspective` roles from satisfying mechanical precedence.
- [Migration complexity for existing rules DBs] -> Preserve book-level scope tags and add new tables in a forward-compatible schema migration.
- [Ingestion gets slower] -> Keep generation local and mostly heuristic; use embeddings only opportunistically when already available.
- [Generated manifests become noisy] -> Human output should summarize counts and top spans; full manifests remain available through JSON/export commands.

## Migration Plan

1. Add schema migration for assertion storage while preserving existing book and chunk fields.
2. Backfill existing book-level `scope_tags_json` as migrated source assertions.
3. Backfill a minimal source assertion for each existing supplement from its current scope tags.
4. Add a rebuild path that can generate finer assertions for already-ingested books without requiring source PDFs when extracted page/chunk text is available.
5. Rebuild FTS/retrieval metadata to include applied chunk scopes where available.
6. Keep rollback simple: existing book-level tags remain intact, so query can fall back to previous behavior if assertion tables are absent or empty.

## Resolved Questions

- SQLite is the only canonical persisted assertion source; YAML manifests are export-on-demand review artifacts.
- The first taxonomy seed is Vampire: The Masquerade terminology across the user's VTM corpus, not all World of Darkness game lines.
- The initial confidence bands are `>= 0.85` auto-applied, `0.60-0.849` suggested, and `< 0.60` diagnostic/ignored for precedence.
- `--scope-tag` is removed from `backet rules ingest`; automatic generation and review/apply commands replace manual ingest-time scope tagging.
