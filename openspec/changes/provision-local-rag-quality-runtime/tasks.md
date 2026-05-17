## 1. Local Runtime Detection

- [x] 1.1 Add runtime detection for Windows, AMD GPU inventory, Ollama command/API availability, and llama.cpp server availability.
- [x] 1.2 Add local runtime doctor output for service roles, model IDs, profile compatibility, and missing install actions.
- [x] 1.3 Add tests with mocked Windows/AMD, missing runtime, and available runtime scenarios.

## 2. Native Ollama Path

- [x] 2.1 Install or detect Ollama on this machine during apply, using the native Windows path first.
- [x] 2.2 Pull and benchmark at least one embedding-capable model and one answer model suitable for the RX 7800 XT / 32 GB RAM machine.
- [x] 2.3 Record exact model IDs, model sizes, backend status, latency, and quality results.

## 3. llama.cpp Vulkan Fallback

- [x] 3.1 Add documentation and optional scripts for llama.cpp Vulkan server setup.
- [x] 3.2 Add config support for a llama.cpp-compatible local completion endpoint.
- [x] 3.3 Use the fallback only if Ollama cannot provide the required service mix or quality.

## 4. Runtime Profiles and Config

- [x] 4.1 Extend bot config/profile parsing for local embedding, reranker, and answer services.
- [x] 4.2 Enforce quality profile fail-closed behavior when required services are missing.
- [x] 4.3 Update `E:/Projects/prague-by-night/.backet/state/bot-config.yaml` to the measured local profile after services pass doctor checks.

## 5. Benchmark and Hardware Guidance

- [x] 5.1 Add a benchmark command that runs QA cases and records latency, throughput, memory, and pass/fail quality.
- [x] 5.2 Generate a hardware recommendation summary from measured local results.
- [x] 5.3 Update deployment/wiki docs with local measured requirements and production hosting guidance.
