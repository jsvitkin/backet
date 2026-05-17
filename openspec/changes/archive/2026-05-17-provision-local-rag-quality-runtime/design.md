## Context

Local hardware inventory:
- CPU: AMD Ryzen 7 7800X3D, 8 cores / 16 logical processors.
- RAM: about 32 GB.
- GPU path: AMD Radeon RX 7800 XT detected by Windows.
- Docker CLI: not currently on PATH.
- NVIDIA tooling: `nvidia-smi` not present.

Official docs indicate Ollama runs natively on Windows with AMD Radeon GPU support and serves a local API on `http://localhost:11434`. Ollama GPU docs list the Radeon RX 7800 XT under Windows AMD support. llama.cpp also supports Vulkan builds, which gives us a lower-level AMD-friendly fallback and future Docker/container route.

Given this machine, the first benchmark path is native Windows Ollama. Docker can be installed later if we need container parity, but using Docker first would add setup friction without improving the immediate quality experiment.

## Goals / Non-Goals

**Goals:**
- Install or detect a local model runtime suitable for AMD Radeon hardware.
- Configure Backet to use real embedding and answer services instead of hash embeddings and template-only answers.
- Benchmark model/resource usage locally before deciding final hosting hardware.
- Keep model files and caches machine-local, not in the repo or vault Git history.
- Provide a fallback path using llama.cpp Vulkan for direct GGUF testing.

**Non-Goals:**
- Do not choose final production hosting before benchmarks.
- Do not rely on remote commercial model APIs.
- Do not require Docker for the first local proof.
- Do not commit downloaded models, model caches, or benchmark scratch artifacts.

## Decisions

1. Native Ollama first.
   - Rationale: it is the quickest path for Windows AMD GPU support on this machine and exposes a simple local HTTP API.
   - Alternative: Docker first. Rejected for first pass because Docker is not installed and GPU acceleration on Windows/AMD containers is more likely to become setup work than answer-quality work.
   - Alternative: build llama.cpp first. Kept as fallback because Vulkan builds are useful, but Ollama should get us to measurable QA faster.

2. Separate model service roles.
   - Embedding, reranking, and answer synthesis are separate runtime roles.
   - This lets us discover whether the answer model, embedding model, or reranker is the bottleneck.

3. Benchmark with QA cases, not synthetic prompts only.
   - The benchmark must report both resource metrics and answer-quality pass/fail.
   - A fast model that fails the Prague QA cases is not acceptable.

4. Store machine-local runtime state outside Git.
   - Suggested default: `%LOCALAPPDATA%/backet/models` or the runtime's own model cache.
   - Per-vault config stores endpoints, profile names, and non-secret model IDs only.

## Risks / Trade-offs

- AMD GPU acceleration can vary by driver/runtime. Mitigation: runtime doctor records detected backend, GPU use, and falls back to CPU only as an explicit degraded state.
- 32 GB system RAM and RX 7800 XT VRAM may limit larger models. Mitigation: benchmark several tiers and report quality/latency/memory trade-offs.
- Ollama model names and availability can change. Mitigation: model choices remain config values and the benchmark command records exact resolved model IDs.
- Reranker support may require a separate Python service. Mitigation: implement reranking as optional for standard profile and required for quality profile only after service validation.

## Migration Plan

During apply, install or detect Ollama first, pull candidate models, start local services, and run the QA workbench. Then update `E:/Projects/prague-by-night/.backet/state/bot-config.yaml` to a local quality profile only after the services pass doctor checks. If benchmarks show hardware limits, keep Prague on standard profile and report the measured gap.

