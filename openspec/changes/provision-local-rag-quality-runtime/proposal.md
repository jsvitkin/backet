## Why

The current Prague bot is configured for template answers and hash embeddings, so the new RAG pipeline cannot show its real ceiling. We need a local high-quality runtime on the user's machine to benchmark answer models, embedding models, reranking, latency, memory use, and deployment requirements before choosing remote or stronger hosting hardware.

## What Changes

- Add a local RAG quality runtime setup for Windows gaming hardware with AMD Radeon GPU support.
- Prefer native Ollama on Windows for the first implementation because this machine has an AMD Radeon RX 7800 XT and Docker is not currently installed.
- Keep llama.cpp Vulkan as the lower-level fallback for direct GGUF server testing and future containerization.
- Add runtime profiles that configure embedding, reranker, and answer services separately.
- Add a local benchmark command that measures model load time, time to first token, tokens per second, answer latency, peak process memory, and pass/fail QA results.
- Update Prague-local bot config during apply to use the local quality profile once services are installed and verified.
- Document the eventual hosting sizing decision from local measurements instead of guessing.

## Capabilities

### New Capabilities
- `local-model-runtime`: Installs, configures, benchmarks, and reports local model services used by Backet bot quality profiles.

### Modified Capabilities
- `bot-deployment-bundles`: Exported bundles carry local runtime service metadata and quality-profile requirements.
- `bot-setup-wizard`: Setup can configure local model endpoints and profile choices without storing secrets.
- `discord-query-bot`: Bot runtime respects local quality profile availability, fallback policy, and benchmark diagnostics.

## Impact

- Affected local machine: may install Ollama or llama.cpp/Vulkan dependencies during apply.
- Affected per-vault state: bot config can be changed to point at local endpoints; model caches stay machine-local and ignored.
- Affected deployment docs: quality profile hardware guidance will be based on measured local resource usage.
- Affected tests: profile parsing, model service doctor, benchmark output, and QA workbench integration.
- Non-goal for this change: production cloud deployment. This change measures and proves the runtime locally first.

