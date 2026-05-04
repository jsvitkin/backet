## Context

Rules ingestion already stores page audit rows, chunk confidence, generated retrieval metadata, source PDF paths, PDF fingerprints, repair history, and semantic index state under each vault's `.backet/rules/` SQLite store. Source PDFs remain outside the vault and are referenced by path and fingerprint only.

The current `backet rules audit` command returns three useful machine signals:

- extraction quality findings from `page_audit`
- low-confidence OCR chunks from `rule_chunks`
- semantic/retrieval index coverage from the current embedding backend

Human output still flows through the generic result printer, so the user sees raw keys such as `suspect_pages`, `suspect_chunks`, and `semantic_index`. There is no durable review state, so the same reviewed page keeps reappearing if the underlying extraction is unchanged. The existing `backet rules repair` command can rescan stored PDF paths, but only as a blunt page-range operation and only when the original source path still exists.

The change is CLI-owned. Skills may learn how to interpret audit status before relying on rules retrieval, but skills do not mutate the rules corpus. The Obsidian vault remains canonical for chronicle content; audit review state is derived rules-corpus maintenance state, not campaign canon.

## Goals / Non-Goals

**Goals:**

- Make non-JSON audit output tell the user what is healthy, what needs review, what can be fixed automatically, and what is merely informational.
- Add a review queue that groups low-confidence chunk findings by page and presents bounded review cards.
- Persist human decisions so accepted, ignored, excluded, retried, and replaced findings do not recur as urgent work while their content hash is unchanged.
- Add source PDF status to audit and make automatic OCR repair depend on an available, verified source PDF.
- Provide local automatic repair for safe maintenance work and OCR retry candidates while leaving ambiguous content decisions to the human.
- Keep `--json` deterministic and detailed for agents and tests.
- Keep retrieval bounded to stored chunks and metadata; review must never imply loading an entire rulebook into model context.

**Non-Goals:**

- Do not copy source PDFs into the vault.
- Do not introduce remote OCR, hosted model calls, telemetry, or rulebook upload behavior.
- Do not normalize rules into a mechanics database.
- Do not create or modify Obsidian notes as part of audit review.
- Do not make scope suggestions automatically authoritative without review.

## Decisions

### 1. Introduce an audit finding model before rendering

`audit_rules()` should still produce deterministic data, but non-JSON rendering should consume a normalized internal finding list rather than directly printing persisted rows. Findings should be categorized into:

```text
health       Automatic maintenance, such as missing embeddings or retrieval metadata.
review       Human decision needed, grouped by book and page.
notice       Informational, low urgency, or likely non-rule material.
blocked      A repairable issue is blocked by missing or mismatched source PDF.
scope        Scope suggestions or scope review counts, shown separately from extraction quality.
```

Why:

- `suspect_chunks` is currently too low-level. A single page can produce several chunks, and OCR confidence alone does not say whether the page matters.
- Grouping by page matches the human review task: compare one page against its extracted text and decide what to do.
- A finding model keeps JSON complete while allowing human output to be smaller and clearer.

Alternative considered:

- Only add a prettier Rich table around the existing data. Rejected because it would still lack durable decisions, source PDF status, and actionable workflow states.

### 2. Persist review decisions keyed to the extracted content hash

Add durable review state to the per-vault rules store, keyed to the finding target and the relevant content hash. A practical shape:

```text
rule_audit_reviews
  id
  book_id
  target_type          page | chunk | source | scope
  page_start
  page_end
  chunk_index          nullable
  finding_kind         low_confidence_ocr | no_text | source_missing | ...
  decision             accepted | ignored | excluded | retried | replaced | skipped
  content_hash
  reason               optional short code
  notes                optional human note
  decided_at
```

When extraction changes and the content hash no longer matches, the prior decision becomes historical rather than suppressing the new finding.

Why:

- The review queue should get quieter as the user works through it.
- Hash-keying prevents an old "ignore" from hiding a newly repaired or newly corrupted page.
- The state belongs in `.backet/rules/` because it is about the ingested rules corpus, not vault canon.

Alternative considered:

- Store review decisions only in a YAML manifest. Rejected for the main workflow because the current rules corpus is SQLite-backed and needs query-time behavior such as retrieval exclusion. Exportable manifests can still be added later.

### 3. Give human decisions distinct retrieval effects

Decision semantics:

```text
accepted
  Keep extracted text and hide the unchanged finding from urgent review.

ignored
  Mark the finding as expected or not worth action; hide the unchanged finding from urgent review.
  Does not by itself make the text authoritative.

excluded
  Keep provenance and audit rows, but exclude affected chunks from rules retrieval.

retried
  Record that the user requested automatic repair; replace only if the new candidate scores better.

replaced
  Use human-provided corrected text for the selected page, regenerate chunks, and refresh retrieval metadata.

skipped
  Keep the finding in the queue, possibly lower in order for the current run only.
```

Retrieval exclusion should be represented durably, either as a review-derived exclusion table or as a stable retrieval metadata flag such as `excluded_by_review`. `backet rules query` must filter excluded chunks before ranking so exact and semantic retrieval agree.

Why:

- "Ignore" and "exclude" are different user intents. Ignore means "stop nagging me"; exclude means "do not use this text in answers."
- Manual replacement needs to behave like a targeted page ingest so query results can use the corrected content immediately.

Alternative considered:

- Make every ignored page disappear from retrieval. Rejected because some ignored audit findings are merely harmless OCR warnings on usable pages.

### 4. Make automatic repair explicit and source-verified

Automatic repair should run only when the stored source PDF is available and safe to use. Audit should show source status for each audited book:

```text
available     stored path exists and fingerprint matches
missing       stored path does not exist
mismatch      stored path exists but fingerprint differs
unverified    fingerprint cannot be computed
```

Repair behavior:

1. Verify source path and fingerprint before OCR retry.
2. Try local extraction/OCR candidates for selected pages:
   - direct text extraction
   - current OCR path
   - higher DPI OCR
   - alternate Tesseract page segmentation mode
   - light grayscale/contrast preprocessing if available without broad dependency churn
3. Score candidates with deterministic quality signals:
   - character count
   - alpha ratio
   - word count
   - strange-symbol ratio
   - rules/domain term presence
   - section classification such as art, title, index, rules, unknown
4. Replace the page only when the best candidate is materially better than current text.
5. If no candidate improves the page, keep or create a human review finding.

Why:

- The CLI can improve extraction quality, but it cannot always know whether an ambiguous page matters.
- Fingerprint verification prevents accidentally repairing an old ingestion with a different PDF layout.

Alternative considered:

- Always rerun `repair_rules()` on every suspect page. Rejected because it can waste time, repeat the same OCR failure, and mutate data without explaining whether the result improved.

### 5. Add source PDF relink as a first-class maintenance action

When the stored source path is missing, audit should show repair as blocked and guide the user to relink or re-ingest. Relink should:

- accept a local PDF path
- compute fingerprint and page count
- mark the source as verified when fingerprint matches the original
- require explicit confirmation for fingerprint mismatch
- preserve enough history to explain which source path was used for later repair

Why:

- Source PDFs remain external by design, so moved files are expected over a long-lived vault.
- Automatic repair depends on source availability; missing PDFs should be clear and resolvable.

Alternative considered:

- Ask users to fully re-ingest whenever a PDF path changes. Rejected because it is unnecessary when the same file moved.

### 6. Keep scope audit separate from extraction audit

`backet rules scope audit` should receive a human summary, but it should remain conceptually distinct:

```text
Extraction audit: "Is the stored text readable and usable?"
Scope audit:      "Are generated topic/authority assertions acceptable?"
```

Scope review should summarize source scope, applied assertions, suggested assertions, rejected assertions, and notable review candidates. Existing export/apply manifest behavior remains the correction path for the first slice.

Why:

- Mixing OCR repair and authority/scope curation would make both workflows harder to reason about.
- Scope assertions affect retrieval precedence and should not be hidden under extraction quality.
- First-class per-suggestion scope accept/reject commands are useful, but they are a separate workflow after the extraction audit review loop is humane.

Alternative considered:

- Fold all scope suggestions into `rules audit`. Rejected because a clean OCR page can still have uncertain scope assertions, and a bad OCR page can still be irrelevant to scope.
- Add one-by-one scope accept/reject commands in this slice. Deferred because scope correction already has export/apply, while extraction audit currently has no humane correction workflow at all.

### 7. Preserve deterministic JSON and bounded human output

Human output should use Rich summaries and bounded tables/cards. Non-JSON `backet rules audit` is the human-first entry point: it should summarize status and, when an interactive terminal has pending reviewable findings, guide the user into the review cards without requiring an agent-style flag. JSON output should continue to expose complete data for agents and tests, including finding categories, review state, source status, and repair hints.

Agent-facing and scripted paths should use explicit flags/options such as `--json`, non-interactive decision commands, `--text-file`, stdin, or other deterministic inputs. Redirected non-JSON output should remain bounded and non-interactive so shell scripts do not hang.

Why:

- Current tests and agent workflows rely on deterministic `--json`.
- The default no-flag experience is for humans, not agents.
- Humans need a readable status first, then a guided way to do the next review action.

Alternative considered:

- Require `backet rules review` or `backet rules audit --review` for the human review flow. Rejected because it makes the humane path feel secondary and command-discovery-heavy.

## Risks / Trade-offs

- [Review state can hide real problems if keyed too broadly] -> Key decisions to content hash and invalidate them when extraction changes.
- [Automatic OCR retry may mutate good-enough data into worse data] -> Score candidates deterministically and only replace on material improvement; otherwise keep the human review card.
- [Fingerprint mismatch may block useful repairs from a better-quality replacement PDF] -> Allow explicit human relink/confirmation while keeping automatic repair conservative.
- [More CLI verbs can make the workflow feel complex] -> Keep the normal path simple: audit summary, review queue, one-card decisions.
- [Manual text replacement can create durable copyrighted rule text in the rules store] -> This is consistent with existing local ingested rules storage from user-owned PDFs, remains local, and is not copied into Obsidian canon notes.
- [Scope audit and extraction audit may drift into two UX styles] -> Share summary/card language while keeping correction mechanisms separate.

## Migration Plan

1. Add compatible SQLite migrations for review decisions, source relink history, manual text overrides, and retrieval exclusions as needed.
2. Backfill nothing by default; existing audit findings start as unreviewed.
3. Treat existing source PDF paths and fingerprints as the initial source status records.
4. Keep old JSON fields for compatibility where practical while adding structured finding/review/source status fields.
5. Roll back by ignoring the new review tables and continuing to query existing page/chunk data; no source PDFs or vault canon files are modified.

## Resolved Follow-Up Decisions

- Non-JSON `backet rules audit` is the default human entry point. Flags and deterministic subcommands are for agents, tests, and scripts.
- Manual replacement should accept all three input styles: inline editor, `--text-file`, and stdin.
- `ignored` means "do not show this unchanged finding as urgent review work"; it does not remove text from retrieval. Retrieval exclusion always requires the explicit `excluded` decision.
- Scope suggestions keep the existing export/apply correction mechanism in this slice. First-class per-suggestion scope accept/reject commands can be proposed later if manifest review proves too clumsy.
