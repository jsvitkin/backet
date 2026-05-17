# backet Wiki

Welcome to the `backet` wiki.

Current release: `v0.2.0`.

## What's New in v0.2.0

This minor release upgrades the private Discord bot from a simple retrieval wrapper into a more explicit RAG runtime:

- Rules questions use query planning, rule-block structure, entity/alias resolution, hybrid retrieval, reranking metadata, and evidence checks before answer synthesis.
- Bot answers are source-grounded, claim-validated, answerability-aware, and include diagnostics for missing evidence, ambiguity, fallback, claim support, and degraded runtime state.
- Deployment now supports `lite`, `rag-standard`, and `rag-quality` runtime profiles so operators can choose between low-resource hosting and stronger self-hosted model services.
- Bundle manifests and doctor output report runtime profile, service health, fallback policy, and degraded mode without storing secrets or model weights.

Start here:

- [[Installation]]
- [[Adding Rules to a Vault]]
- [[Hosting Backet Bot]]
