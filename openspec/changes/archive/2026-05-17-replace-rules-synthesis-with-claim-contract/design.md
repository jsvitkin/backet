## Context

The local sandbox run showed the most painful failure mode: evidence sometimes contained the correct rule, but the visible answer selected an irrelevant sentence. The current deterministic fallback is sentence extraction with heuristics. It is useful as a safety net, but it is not an answerability proof. We need an explicit intermediate object: a supported claim that says exactly what the answer is, where it came from, and which part of the question it covers.

The CLI/runtime owns claim extraction and final answer composition. Optional local models may help propose or judge claims, but deterministic validation decides whether final text can be shown. Discord output remains compact and source-grounded.

## Goals / Non-Goals

**Goals:**

- Build final answers from validated supported claims, not raw first-source snippets.
- Abstain when no claim directly covers the planned entity, intent, stance, and target constraints.
- Allow local models to assist with bounded extraction/judging while preventing unsupported prose from reaching Discord.
- Make QA failures explain whether retrieval, claim extraction, model validation, or final composition failed.

**Non-Goals:**

- Do not implement an unconstrained chat-answer generator.
- Do not send source text to remote services.
- Do not require model synthesis for lite or deterministic profiles.

## Decisions

1. Claims become the synthesis boundary.
   - Decision: answer synthesis consumes a list of claim objects, each with text, source IDs, support spans, covered intents, stance, constraints, and validation status.
   - Rationale: final prose can be simple if the claim contract is trustworthy.
   - Alternative considered: improve sentence scoring. Rejected because the Hunger 5 failure showed sentence scoring can see the right paragraph and still choose the wrong sentence.

2. Deterministic composer is claim-based.
   - Decision: the fallback path formats validated claims directly and abstains without them.
   - Rationale: fallback should be boring and correct, not clever and brittle.

3. Optional model roles are bounded.
   - Decision: local models may rank evidence, propose claims, or judge support, but every proposed claim must cite selected evidence and pass deterministic support checks.
   - Rationale: a stronger model helps with interpretation but should not become a hidden source of unsupported rules text.

4. Validation is stricter than citation presence.
   - Decision: final output must cover the required claim/stance and cite available selected sources. Missing citation, missing claim support, unsupported stance, or answerability mismatch rejects the output.
   - Rationale: the current validator catches citation problems but cannot yet guarantee the fallback claim is the right one.

## Risks / Trade-offs

- [Risk] Claim extraction is initially conservative and abstains more often. → Mitigation: QA reports show missing claim coverage so resolver/retrieval gaps can be fixed intentionally.
- [Risk] Support-span checks are hard on OCR text. → Mitigation: use bounded normalized spans and source IDs rather than exact quote-only matching.
- [Risk] Model-assisted extraction adds latency. → Mitigation: keep deterministic extraction available and profile model roles separately.

## Migration Plan

1. Define claim schema and diagnostics.
2. Implement deterministic claim extraction from selected evidence.
3. Replace fallback composer with claim-based formatting.
4. Add optional local model extraction/judge hooks behind config/profile flags.
5. Tighten validation and expand QA cases to require claim support.

## Open Questions

- None. The architectural decision is that final answers must be claims with support, whether those claims are extracted deterministically or proposed by a local model.
