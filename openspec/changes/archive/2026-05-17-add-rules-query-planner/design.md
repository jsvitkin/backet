## Context

The current rules query path tokenizes the raw question and builds an FTS query using `OR` across remaining terms. This makes user phrasing disproportionately powerful. In the observed failures:

- "learn Obfuscate" matched a chunk containing "learn a lesson" plus an Obfuscate listing.
- "bloodbonds" missed "blood bond" and let generic terms like "use" compete.
- "Malkavians use Dementation on other vampires" needed targeting/system evidence, not merely a clan or discipline mention.

The planner sits between user input and retrieval:

```text
raw question
  -> query planner
     -> intent
     -> canonical entities
     -> scope tags
     -> expanded retrieval queries
     -> required evidence hints
  -> rules retrieval
```

## Goals / Non-Goals

**Goals:**
- Normalize common VTM rules language before retrieval.
- Infer the evidence type needed by the question.
- Convert detected clans, disciplines, sects, mechanics, powers, and aliases into structured query-plan fields.
- Produce multiple bounded retrieval queries for later candidate generation.
- Expose the plan in diagnostics for humans, agents, and regression tests.
- Keep planning local and deterministic in the first slice.

**Non-Goals:**
- Do not replace the retrieval ranking engine in this change.
- Do not require a local Llama or hosted LLM for planning.
- Do not build a complete mechanical ontology for every VTM rule.
- Do not answer from the query plan alone; the plan only guides retrieval.
- Do not broaden access scope or bypass existing bot authorization.

## Decisions

### Decision: Use a deterministic planner first

The initial planner should be rules-based and data-driven:

- token normalization and decompounding
- alias tables sourced from the existing rules scope taxonomy
- a small mechanics alias table for common terms not currently in the taxonomy
- intent patterns for common question shapes
- stopword handling tuned for rules questions

Rationale: deterministic planning is testable, local, cheap, and does not require a better hosting environment. It also creates a stable input contract for RAG v2.

Alternative considered: immediately using an LLM planner. That may become useful later, but it would make failures harder to reproduce and would tie a foundational retrieval stage to hosting before diagnostics exist.

### Decision: Represent plans as structured data, not rewritten strings only

A plan should include at least:

```text
raw_question
normalized_question
intents
entities
scope_tags
canonical_terms
expanded_terms
retrieval_queries
required_evidence
low_value_terms
warnings
```

Rationale: downstream retrieval, diagnostics, tests, and answerability gates need to know why a query exists. A rewritten string would hide too much.

Alternative considered: simple query expansion list. That helps exact search, but does not tell the answer layer whether it needs definition, advancement, targeting, or cost evidence.

### Decision: Planner output is transient by default

Plans should be emitted in diagnostics and used during retrieval, but they should not be stored as canonical vault state. Any alias tables or taxonomies live in code or versioned per-vault rule metadata, not in human-authored notes.

Rationale: the user question is ephemeral. The vault should remain the source of campaign canon, not a store of every bot question.

### Decision: Treat user phrasing as evidence, not authority

The raw question remains useful, but the planner should identify low-value terms and avoid letting them dominate retrieval. In the screenshot cases, terms like "learn", "make", "use", "other", and "it" should not outrank canonical terms like `blood bond`, `discipline:obfuscate`, or `power:dementation`.

Rationale: this directly addresses the observed failure mode without special-casing only those three prompts.

### Decision: Planner should be access-neutral

The planner can identify hidden-looking entities, but it must not choose vault access scope. Authorization and command routing remain in the bot runtime before retrieval.

Rationale: planning should improve retrieval within the already-authorized corpus, not become a permissions layer.

## Risks / Trade-offs

- Deterministic patterns may miss unusual phrasing -> expose warnings and preserve raw question fallback queries with lower weight.
- Alias tables can become stale -> keep them small, test-driven, and tied to existing taxonomy where possible.
- Planner may over-normalize a term with multiple meanings -> retain original terms and emit ambiguity warnings rather than deleting the raw wording.
- Query planning could hide exact user intent -> diagnostics must show both raw and normalized query data.

## Migration Plan

1. Add planner as an internal stage that emits diagnostics but can initially run in observation mode.
2. Feed planned retrieval queries into existing rules retrieval while preserving raw query fallback.
3. Add regression cases for the observed screenshot prompts.
4. Tighten retrieval weighting only after diagnostics prove the planner is producing useful plans.

Rollback can disable planned retrieval and continue using the raw query path, while retaining harmless diagnostic output if desired.

## Open Questions

- None requiring user input. The architecture decision is deterministic local planning first, with model-assisted planning deferred until diagnostics and retrieval contracts exist.
