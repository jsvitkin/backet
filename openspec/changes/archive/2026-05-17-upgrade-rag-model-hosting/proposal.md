## Why

The current free-hosting-friendly runtime is useful for basic template answers, but RAG v2 may need stronger local model services for semantic embeddings, reranking, and answer synthesis. Hosting should become an explicit quality profile decision rather than an accidental limitation of the first Oracle Always Free deployment.

## What Changes

- Add deployment/runtime profiles for lightweight and quality-oriented RAG operation.
- Make embedding, reranker, and answer model services explicit deployable dependencies with health checks.
- Preserve private-data boundaries: bot bundles contain private indexes and rules chunks, but source PDFs, credentials, and model caches remain outside bundles.
- Add preflight and doctor diagnostics for model-service compatibility before deployment.
- Keep the current low-resource template path as a supported fallback profile.
- Avoid hard-coding a single recommended model as the product contract; model choices are operator configuration validated by capability checks.

## Capabilities

### New Capabilities

### Modified Capabilities
- `bot-deployment-bundles`: Deployment bundles and helpers gain RAG runtime profile metadata, model service compatibility checks, and safer fallback behavior.

## Impact

- Affects bot setup, bot export/doctor, deploy assets, docs, and runtime health checks.
- May require new optional dependencies or container services for embeddings, reranking, or answer synthesis.
- Does not put model files, source PDFs, or secrets into Git or bot bundles.
- Does not require a third-party hosted API in the initial slice.
- CLI owns setup and doctor checks; deployment assets own service wiring; skills remain unaffected.
