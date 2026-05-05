## 1. Data Model And Audit Classification

- [x] 1.1 Add compatible rules-store schema migrations for durable audit review decisions keyed to book, target, finding kind, decision, and content hash
- [x] 1.2 Add durable storage for retrieval exclusions produced by audit review decisions
- [x] 1.3 Add durable storage for manual page text overrides or replacement provenance
- [x] 1.4 Add source PDF relink/history storage if existing `books.pdf_path` and `pdf_fingerprint` are not enough to explain current repair status
- [x] 1.5 Define internal dataclasses or structured helpers for audit findings, source PDF status, review decisions, and repair eligibility
- [x] 1.6 Build a normalizer that groups page-level and low-confidence chunk findings into page-based audit cards
- [x] 1.7 Categorize audit findings into maintenance, review, notice, blocked, and scope lanes
- [x] 1.8 Ensure reviewed findings are suppressed from urgent review only when their stored content hash still matches current extracted content

## 2. Human Audit Output

- [x] 2.1 Add a dedicated non-JSON `backet rules audit` renderer instead of using the generic result printer for human output
- [x] 2.2 Render per-book audit summaries with counts for pages, OCR fallback, reviewable pages, low-confidence chunks, source PDF status, and index health
- [x] 2.3 Render bounded review previews grouped by book and page without dumping raw nested diagnostic keys
- [x] 2.4 Render maintenance findings separately from human review findings, including missing/stale embedding and retrieval metadata cases
- [x] 2.5 Render notices for likely art/title/blank/index pages and OCR fallback pages that do not need immediate action
- [x] 2.6 Preserve deterministic `--json rules audit` output while adding structured source status, finding category, review state, and repair eligibility fields
- [x] 2.7 Add a dedicated non-JSON `backet rules scope audit` renderer that summarizes applied/suggested/rejected scope assertions and bounded notable suggestions

## 3. Guided Review Workflow

- [x] 3.1 Make non-JSON `backet rules audit` the human-first entry point that summarizes findings and guides interactive terminals toward pending review cards
- [x] 3.2 Implement a review queue builder that returns only unresolved reviewable findings for the selected vault/book scope
- [x] 3.3 Render one bounded review card at a time with book, page, reason, source status, extracted text preview, and allowed decisions
- [x] 3.4 Persist `accepted` decisions and hide unchanged accepted findings from later urgent review queues
- [x] 3.5 Persist `ignored` decisions and hide unchanged ignored findings from later urgent review queues without automatically making text authoritative or excluding it from retrieval
- [x] 3.6 Persist `excluded` decisions and connect them to retrieval exclusion state
- [x] 3.7 Support `skipped` decisions without resolving the underlying finding
- [x] 3.8 Provide non-interactive decision commands or flags for agents, tests, and scripted review

## 4. Source PDF Status And Relink

- [x] 4.1 Implement source PDF status inspection for available, missing, mismatched, and unverified source states
- [x] 4.2 Include source PDF repair eligibility in audit JSON and human output
- [x] 4.3 Implement a source relink command or option that updates the stored PDF path when the fingerprint matches the original source
- [x] 4.4 Require explicit confirmation or force behavior before using a mismatched replacement PDF for repair
- [x] 4.5 Record enough relink status or history for later audits to explain the current source path and repair safety
- [x] 4.6 Add error handling for missing, unreadable, non-PDF, or fingerprint-failing relink targets

## 5. Automatic Repair And Manual Replacement

- [x] 5.1 Refactor targeted page repair so automatic OCR retry can evaluate candidate extraction outputs before replacing stored text
- [x] 5.2 Add deterministic candidate scoring for text density, alpha ratio, word count, strange-symbol ratio, rules/domain term presence, and section kind
- [x] 5.3 Add local OCR retry candidates such as higher DPI and alternate Tesseract page segmentation while avoiding remote services
- [x] 5.4 Replace stored page/chunk data only when an automatic repair candidate scores materially better than current extraction
- [x] 5.5 Keep or create a human review finding when automatic repair cannot improve a page
- [x] 5.6 Implement manual page text replacement from inline editor input, `--text-file`, and stdin
- [x] 5.7 Reject empty or unusable manual replacement text unless the user chooses ignore or exclude instead
- [x] 5.8 Regenerate page audit rows, chunks, FTS rows, retrieval metadata, scope application, and semantic index coverage for repaired or replaced pages
- [x] 5.9 Record repair/replacement decisions in audit review state with current content hashes

## 6. Retrieval Behavior

- [x] 6.1 Apply review-derived retrieval exclusions before exact, semantic, merged, primary, and fallback rules query ranking
- [x] 6.2 Include deterministic JSON metadata that explains reviewed exclusions when they affect query eligibility
- [x] 6.3 Ensure excluded chunks remain present in audit/provenance data even though they are not query candidates
- [x] 6.4 Verify repair and manual replacement refresh retrieval metadata consistently with existing hybrid retrieval behavior

## 7. Tests

- [x] 7.1 Add schema migration tests for review decisions, exclusions, replacement provenance, and source relink state
- [x] 7.2 Add unit tests for audit finding normalization, category assignment, review-decision suppression, and content-hash invalidation
- [x] 7.3 Add human output tests proving `rules audit` shows bounded summaries and does not expose raw nested diagnostic keys
- [x] 7.4 Add JSON output tests proving deterministic source status, finding categories, review state, and repair hints
- [x] 7.5 Add CLI tests for accepting, ignoring, excluding, skipping, and re-showing changed findings
- [x] 7.6 Add source PDF status and relink tests for available, missing, matching relink, mismatched relink, and unreadable targets
- [x] 7.7 Add automatic repair tests for improved OCR candidates, no-improvement candidates, and blocked missing-source cases
- [x] 7.8 Add manual replacement tests proving page chunks, audit metadata, FTS, retrieval metadata, and query results use corrected text
- [x] 7.9 Add query tests proving excluded chunks do not appear in exact, semantic, primary, or fallback results
- [x] 7.10 Add scope audit output tests for bounded human summaries and preserved deterministic JSON/export behavior

## 8. Documentation And Skill Guidance

- [x] 8.1 Update README rules audit documentation with the new summary, review, repair, replace, exclude, and relink workflow
- [x] 8.2 Document the difference between extraction audit, scope audit, automatic maintenance, notices, and human review decisions
- [x] 8.3 Update relevant workflow skill guidance so agents check audit/source status before relying on rules retrieval when appropriate
- [x] 8.4 Ensure skill updates remain independent from the CLI release and do not require skills to mutate rules corpus state

## 9. Validation

- [x] 9.1 Run the focused rules and rules-output test suites
- [x] 9.2 Run the full Python test suite
- [x] 9.3 Run OpenSpec validation for `improve-rules-audit-review-flow`
- [x] 9.4 Run or update smoke-install coverage if command surfaces or persisted rules-state migrations affect installed CLI behavior
