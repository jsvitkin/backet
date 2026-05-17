## Context

The previous diagnostics change introduced answer quality helpers, but they are only exercised by unit tests. Real bot questions can still pass through planner, retrieval, answerability, and template synthesis with an "answerable" trace even when the visible answer is wrong or useless.

The QA workbench becomes the first layer in the new quality push. It is deliberately CLI-owned because it needs to export bundles, invoke the runtime, read traces, and produce deterministic JSON. Skills can call it, but should not reimplement evaluation logic. Per-vault QA outputs are derived reports, not canonical campaign content.

## Goals / Non-Goals

**Goals:**
- Run realistic player and Storyteller questions against a vault or bot bundle.
- Classify failures by stage: planner, retrieval, answerability, synthesis, citation, runtime.
- Preserve paste-safe, bounded reports for Discord-bot debugging.
- Support a small committed regression suite without embedding copyrighted rulebook text.
- Support optional vault-local QA suites for Prague by Night or other private vaults.

**Non-Goals:**
- Do not judge every possible Vampire: The Masquerade rules question.
- Do not use an external paid evaluation service.
- Do not store source PDFs or long rulebook excerpts in the repo.
- Do not change retrieval or synthesis behavior in this change; this workbench measures those later changes.

## Decisions

1. Add a case-file format rather than hard-code questions.
   - Rationale: the same harness can run public synthetic tests and private Prague tests.
   - Alternative: embed tests in pytest only. Rejected because the user needs a local QA command for real vaults.

2. Evaluate both stages and final answer.
   - Rationale: "bad answer" is too vague. We need to know whether the planner lost an entity, retrieval ranked a mere mention, answerability over-trusted evidence, or synthesis ignored good evidence.
   - Alternative: score only final text. Rejected because it repeats the current black-box debugging problem.

3. Keep expected source anchors small.
   - Rationale: source PDFs remain user-owned. Fixtures can require book IDs, page ranges, section labels, and short non-copyrightable anchor terms without copying source passages.
   - Alternative: store golden excerpts. Rejected for copyright and portability.

4. Make the workbench command both human-readable and JSON-stable.
   - Rationale: humans need a quick pass/fail summary; agents need exact failure details.
   - Alternative: JSON only. Rejected because the project requires concise interpreted terminal output.

## Risks / Trade-offs

- Case expectations can become brittle when page extraction changes. Mitigation: allow page ranges and anchor groups instead of single exact snippets.
- Some private-vault cases cannot run in CI. Mitigation: split committed synthetic cases from local case packs and report skipped private cases explicitly.
- False positives are possible when a terse answer is acceptable. Mitigation: combine required stance, source anchors, and forbidden patterns rather than relying on a single text matcher.
- QA can slow development. Mitigation: provide quick, standard, and full suites.

## Migration Plan

No user data migration is required. Existing `tests/fixtures/answer-quality/cases.json` can become the seed for the new case schema. Prague-local cases can live outside the repo or under the vault's `.backet/qa/` folder.

