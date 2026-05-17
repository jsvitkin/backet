# Adding Rules to a Vault

This guide explains how to feed rulebook PDFs into a `backet`-initialized Obsidian vault.

The short version:

1. Create or choose an existing Obsidian vault directory.
2. Run `backet init` once for that vault.
3. Run `backet rules ingest` for each rulebook PDF you want `backet` to search.
4. Use `backet rules query`, `backet rules audit`, `backet rules repair`, and `backet rules index` as needed.

`backet init` prepares the vault for rule storage, but it does not ingest any rulebooks by itself.

## What `backet init` creates

Initialize the vault first:

```bash
mkdir -p /path/to/vault
backet init /path/to/vault
```

On Windows PowerShell:

```powershell
mkdir C:\path\to\vault
backet init C:\path\to\vault
```

Initialization creates a `.backet/` folder inside the vault. The rules-related parts are:

- `.backet/rules/` for the ingested rule corpus.
- `.backet/rules/rules.sqlite3` after the first rulebook is ingested.
- `.backet/ocr-work/` as rebuildable OCR working space.

The source PDF files stay outside the vault. `backet` reads them, extracts searchable text, and stores the ingested result under `.backet/rules/`.

## Before ingesting rules

Make sure you have:

- A working `backet` install.
- A vault that has already been initialized with `backet init`.
- Local PDF files for the books you want to ingest.
- Permission to use those PDFs for your own local campaign tooling.

PDF text extraction uses PyMuPDF, which is installed with `backet`.

If a PDF is image-only or has poor embedded text, `backet` may need OCR. OCR fallback requires Tesseract on the local machine.

Check the local system dependency state with:

```bash
backet setup check
```

Install or update supported system dependencies with:

```bash
backet setup install --yes
```

On macOS:

```bash
brew install tesseract
```

On Debian or Ubuntu Linux:

```bash
sudo apt-get install tesseract-ocr
```

On Windows, Backet uses WinGet and the UB Mannheim Tesseract package. If PATH has not refreshed yet, Backet also checks the normal `C:\Program Files\Tesseract-OCR\tesseract.exe` install location.

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact --source winget
```

## Ingest a core rulebook

Use `backet rules ingest` with a stable `--book-id`.

```bash
backet rules ingest /path/to/vault /path/to/core-rulebook.pdf \
  --book-id core-v5 \
  --title "Core Rulebook" \
  --tier core
```

Recommended `--book-id` style:

- Use lowercase letters, numbers, and hyphens.
- Keep it stable over time.
- Use a short name you will recognize in query output, such as `core-v5`, `camarilla`, or `players-guide`.

The `--title` is the human-readable display name. If you omit it, `backet` uses the PDF filename stem.

## Ingest supplements with scope tags

Supplements need at least one `--scope-tag`.

```bash
backet rules ingest /path/to/vault /path/to/camarilla.pdf \
  --book-id camarilla \
  --title "Camarilla" \
  --tier supplement \
  --scope-tag camarilla
```

Scope tags help `backet` decide which supplement should take precedence for a query.

You can add more than one scope tag:

```bash
backet rules ingest /path/to/vault /path/to/players-guide.pdf \
  --book-id players-guide \
  --title "Players Guide" \
  --tier supplement \
  --scope-tag disciplines \
  --scope-tag merits
```

Use tags that describe when the book should be preferred: `camarilla`, `sabbat`, `thin-blood`, `disciplines`, `merits`, `blood-sorcery`, and so on.

## Ingest only selected pages

For large books or a quick test, use `--pages`.

```bash
backet rules ingest /path/to/vault /path/to/core-rulebook.pdf \
  --book-id core-v5 \
  --title "Core Rulebook" \
  --tier core \
  --pages 120-135,220
```

The page expression accepts whole page numbers and ranges, for example `3-5,9`.

## Query ingested rules

Search all ingested rules:

```bash
backet rules query /path/to/vault "feeding rights blood doll"
```

Ask for machine-readable JSON:

```bash
backet --json rules query /path/to/vault "feeding rights blood doll"
```

Restrict the query to one book:

```bash
backet rules query /path/to/vault "feeding rights blood doll" \
  --book-id core-v5
```

Prefer a supplement scope:

```bash
backet rules query /path/to/vault "feeding rights blood doll" \
  --scope-tag camarilla
```

When a supplement matches the requested scope, `backet` returns supplement results as primary results and core results as fallback results. If several supplement books match with comparable precedence, `backet` asks you to narrow the query with `--book-id` or more specific `--scope-tag` filters instead of guessing.

In v0.2.0, rules queries run through the RAG v2 retrieval path. Backet plans the query, resolves common rule entities and aliases, combines exact search with semantic matches when embeddings are available, reranks bounded candidates, and builds an evidence packet before answer synthesis. JSON output includes the query plan, resolved entities, unresolved terms, target groups, retrieval mode, embedding backend/model, candidate counts, evidence status, selected evidence, fallback context, and corpus blockers. If semantic retrieval or evidence checks are unavailable, Backet falls back explicitly instead of silently pretending the stronger path ran.

The rules store also derives rule units from chunks. A rule unit is a rebuildable mechanics record that keeps source book/page/chunk links but classifies the passage as a base rule, specific power, ritual, table row, exception, example, or flavor/lore and records facets such as cost, dice pool, target, duration, prerequisite, consequence, and effect. Queries use these units as an additional bounded retrieval channel so an example or nearby lore paragraph is less likely to outrank an actual rule.

Inspect rule-unit coverage with:

```bash
backet rules units /path/to/vault
```

Inspect one unit:

```bash
backet rules units /path/to/vault --unit-id core-v5:unit:p214:c2:ritual-ward-against-kindred:abc123def4
```

The evidence packet is also used by the Discord bot. The bot now composes final text from validated answer claims over selected evidence, not from arbitrary fallback snippets. If the retrieved chunks are merely related but do not contain answer evidence, the bot should refuse with a missing-evidence answer instead of summarizing the wrong passage.

## Refresh semantic indexes

Run `backet rules index` after installing or changing the optional Sentence Transformers backend, after restoring an older rules store, or when `backet rules audit` reports stale semantic coverage, stale rule-block structure, stale entity catalog data, or stale rule units.

```bash
backet rules index /path/to/vault
```

Refresh one book:

```bash
backet rules index /path/to/vault --book-id core-v5
```

Rebuild all rule embeddings, rule-block structure, entity catalog entries, derived retrieval-quality metadata, and rule units:

```bash
backet rules index /path/to/vault --full
```

## Audit extraction quality

After ingesting PDFs, run:

```bash
backet rules audit /path/to/vault
```

Audit output reports pages and chunks that look suspicious, such as pages with very little extracted text or OCR fallback. It also reports rule-block structure health, stale metadata, and whether the store can be fixed with `backet rules index --full` or needs source-PDF reingestion.

Audit one book:

```bash
backet rules audit /path/to/vault --book-id core-v5
```

## Repair weak pages

If audit shows bad pages, repair a targeted page range.

```bash
backet rules repair /path/to/vault core-v5 --pages 120-122 --force-ocr
```

Repair uses the source PDF path remembered during ingestion. If you moved the PDF after ingesting it, either move it back to the original path or re-ingest the book from its new location.

## What should be backed up

Back up or commit the vault's `.backet/` durable state along with the vault if you want the ingested rule corpus to travel with the campaign.

Important details:

- Keep the original PDFs outside the vault.
- `.backet/rules/rules.sqlite3` contains the extracted, searchable rules corpus.
- `.backet/cache/`, `.backet/temp/`, and `.backet/ocr-work/` are local rebuildable working directories.
- `backet doctor /path/to/vault` checks whether expected vault state is present.
- `backet doctor --fix /path/to/vault` can recreate safe local working directories, the scoped `.backet/.gitignore`, and the root `.backetignore` index policy when they are missing.

## Common first-time flow

```bash
# 1. Create or choose your Obsidian vault.
mkdir -p /path/to/vault

# 2. Initialize backet in that vault.
backet init /path/to/vault

# 3. Add the core rules.
backet rules ingest /path/to/vault /path/to/core-rulebook.pdf \
  --book-id core-v5 \
  --title "Core Rulebook" \
  --tier core

# 4. Add a supplement with a scope tag.
backet rules ingest /path/to/vault /path/to/camarilla.pdf \
  --book-id camarilla \
  --title "Camarilla" \
  --tier supplement \
  --scope-tag camarilla

# 5. Check extraction quality.
backet rules audit /path/to/vault

# 6. Try a query.
backet rules query /path/to/vault "feeding rights blood doll" --scope-tag camarilla
```

After this, workflow skills and manual commands can use `backet rules query` to pull bounded rule references without loading whole books into a prompt.

## Troubleshooting

`Vault is not bootstrapped for backet yet.`

Run `backet init /path/to/vault` first.

`Supplement rulebooks need at least one scope tag.`

Re-run ingestion with one or more `--scope-tag` values.

`Rulebook PDF not found.`

Check the PDF path. The source PDF must be readable from the machine running `backet`.

`OCR fallback is required for this PDF, but Tesseract is not available.`

Run `backet setup check` to confirm the missing dependency. On supported platforms, run `backet setup install --yes`, then open a new terminal if the installer changed `PATH` and rerun the ingestion or repair command.

`Multiple supplement-specific rulebooks match this query with comparable precedence.`

Narrow the query with `--book-id` or add more specific `--scope-tag` filters.
