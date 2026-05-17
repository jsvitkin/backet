## Context

The current deployment story targets a private Oracle Always Free VM with a bot container and optional local Llama service. That was appropriate for the initial bot, but answer quality work changes the runtime profile:

- query planning can run locally and cheaply
- RAG v2 retrieval benefits from real embeddings and may benefit from reranking
- answer synthesis may benefit from a stronger local model
- low-resource deployments still need a correct fallback path

This change makes runtime capabilities explicit:

```text
profile: lite
  template answers
  exact / degraded semantic retrieval
  no heavy model requirement

profile: rag-standard
  real embedding backend
  deterministic or lightweight reranker
  optional local answer model

profile: rag-quality
  real embedding backend
  stronger reranker service
  stronger local answer model
  stricter health and latency checks
```

Model names should remain configuration, not normative spec. The product contract should describe required capabilities, privacy boundaries, health checks, and fallbacks.

## Goals / Non-Goals

**Goals:**
- Make hosting requirements visible before deployment.
- Support the current free or low-resource path as a fallback profile.
- Support stronger self-hosted RAG services for embeddings, reranking, and answer synthesis.
- Keep private source material inside user-controlled infrastructure.
- Add doctor checks that fail clearly when configured services are missing, incompatible, or too slow.
- Keep bundle export deterministic and read-only.

**Non-Goals:**
- Do not require a commercial remote LLM API in the initial slice.
- Do not choose a permanent single model family in the spec.
- Do not bundle model weights in bot data bundles or Git.
- Do not make hosted runtime mutate canonical vault or rules state.
- Do not force every user off the free profile if they accept lower quality or template-only operation.

## Decisions

### Decision: Use runtime profiles instead of one hosting answer

Deployment configuration should include a RAG runtime profile. The profile controls required services, health checks, and fallback behavior.

Rationale: users may be in different phases. A Storyteller testing the bot can use `lite`; a production table that wants better answers can move to `rag-standard` or `rag-quality`.

Alternative considered: remove free hosting support. That would simplify support but make the bot harder to adopt and test.

### Decision: Keep model services self-hosted for the first upgrade

The initial hosting upgrade should support local or self-hosted services reachable by the bot deployment:

- embedding service or local embedding backend
- optional reranker service
- optional answer model service

Remote commercial APIs can be explored later behind an explicit privacy and licensing decision.

Rationale: rule chunks and vault canon are private and may include copyrighted rulebook-derived text. Self-hosting keeps the current privacy boundary intact.

Alternative considered: support hosted APIs immediately. That might improve quality quickly, but it would require a separate policy decision about sending private/copyrighted corpus snippets to a third party.

### Decision: Validate capabilities, not model names

Doctor checks should validate configured services by capability:

- can embed sample text with expected dimensions and model identifier
- can rerank a small candidate set if reranking is enabled
- can produce bounded completion if answer synthesis is enabled
- meets configured timeout and health thresholds
- matches bundle compatibility metadata

Rationale: model recommendations age quickly. Capability checks remain useful when model names change.

### Decision: Runtime must degrade according to profile policy

Each profile should define what happens when a model service is unavailable:

- `lite`: no model services required; template output remains available
- `rag-standard`: degraded retrieval or template fallback allowed with explicit diagnostics
- `rag-quality`: fail closed or refuse answer if required services are unavailable

Rationale: silent degradation is one reason quality issues are hard to diagnose. The operator should know whether the bot is answering in a lower-quality mode.

### Decision: Keep hosted runtime read-only

The hosted VM should not ingest PDFs, rebuild canonical indexes, or repair OCR. It can read bundled indexes and call model services. Canonical maintenance remains local, followed by export and redeploy.

Rationale: this preserves the existing source-of-truth model and keeps the VM from becoming a second mutable vault.

## Risks / Trade-offs

- More profiles increase setup complexity -> guided setup and doctor output should explain the selected profile and missing services.
- Self-hosted quality models may cost money or require more RAM/CPU/GPU -> docs should describe capability classes and validation, not promise cheap performance.
- Service health checks may pass but answers may still be poor -> answer-quality regression cases remain the quality gate.
- Remote APIs might be desirable later -> leave extension points, but do not include them in the initial contract.
- Profile drift between local export and hosted runtime can break retrieval -> store runtime compatibility metadata in the bundle manifest and check it at startup.

## Migration Plan

1. Add profile metadata to setup/export/doctor without changing current default behavior.
2. Mark current deployment as `lite` unless configured otherwise.
3. Add service health checks and manifest compatibility checks.
4. Add deploy assets for optional embedding, reranker, and answer model service endpoints.
5. Document upgrade path from `lite` to stronger profiles.

Rollback can set the profile back to `lite` and keep template fallback active.

## Open Questions

- None requiring user input. The architecture decision is self-hosted capability profiles first, with third-party hosted APIs deferred to a separate privacy and licensing discussion if desired later.
