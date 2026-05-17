from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from backet.bot_profiles import (
    DEFAULT_ENDPOINT_ENV,
    RUNTIME_PROFILE_LITE,
    RUNTIME_PROFILE_RAG_QUALITY,
    RUNTIME_PROFILE_RAG_STANDARD,
    SERVICE_ROLE_ANSWER,
    SERVICE_ROLE_EMBEDDING,
    SERVICE_ROLE_RERANKER,
    parse_runtime_profile_config,
)
from backet.errors import AppError
from backet.models import CommandResult, Issue

DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_OLLAMA_ANSWER_MODEL = "llama3.2:3b"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 60.0
DEFAULT_MODEL_CACHE_WINDOWS = "H:/OllamaModels"
LLAMA_CPP_ENDPOINT = "http://127.0.0.1:8080/completion"


def local_runtime_doctor(
    *,
    endpoint: str | None = None,
    embedding_model: str | None = None,
    answer_model: str | None = None,
    model_cache: Path | None = None,
    config: dict[str, Any] | None = None,
) -> CommandResult:
    resolved_endpoint = _normalize_endpoint(endpoint)
    resolved_embedding_model = embedding_model or _configured_model(config, SERVICE_ROLE_EMBEDDING) or DEFAULT_OLLAMA_EMBEDDING_MODEL
    resolved_answer_model = answer_model or _configured_model(config, SERVICE_ROLE_ANSWER) or DEFAULT_OLLAMA_ANSWER_MODEL
    resolved_cache = str(model_cache or os.environ.get("OLLAMA_MODELS") or _default_model_cache_path())

    hardware = _hardware_inventory()
    ollama = _ollama_status(
        endpoint=resolved_endpoint,
        embedding_model=resolved_embedding_model,
        answer_model=resolved_answer_model,
        model_cache=resolved_cache,
    )
    llama_cpp = _llama_cpp_status()
    profile_config = parse_runtime_profile_config(config or {})
    compatibility = _profile_compatibility(
        ollama=ollama,
        config=config or {},
        profile=profile_config.profile,
        embedding_model=resolved_embedding_model,
        answer_model=resolved_answer_model,
    )

    issues = _runtime_issues(ollama, llama_cpp, compatibility)
    ok = ollama["api_available"] and compatibility["profiles"][RUNTIME_PROFILE_RAG_STANDARD]["compatible"]
    data = {
        "ok": ok,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "hardware": hardware,
        "ollama": ollama,
        "llama_cpp": llama_cpp,
        "runtime_profile": profile_config.to_config(),
        "profile_compatibility": compatibility,
    }
    return CommandResult(message="Local RAG runtime doctor complete", issues=issues, data=data)


def run_local_runtime_benchmark(
    target: Path | None = None,
    *,
    case_files: list[Path] | None = None,
    endpoint: str | None = None,
    embedding_model: str | None = None,
    answer_model: str | None = None,
    model_cache: Path | None = None,
    command: str = "rules.ask",
    role_ids: list[str] | None = None,
    user_id: str | None = None,
    limit: int = 4,
    report_output: Path | None = None,
    config: dict[str, Any] | None = None,
) -> CommandResult:
    resolved_endpoint = _normalize_endpoint(endpoint)
    resolved_embedding_model = embedding_model or _configured_model(config, SERVICE_ROLE_EMBEDDING) or DEFAULT_OLLAMA_EMBEDDING_MODEL
    resolved_answer_model = answer_model or _configured_model(config, SERVICE_ROLE_ANSWER) or DEFAULT_OLLAMA_ANSWER_MODEL
    doctor = local_runtime_doctor(
        endpoint=resolved_endpoint,
        embedding_model=resolved_embedding_model,
        answer_model=resolved_answer_model,
        model_cache=model_cache,
        config=config,
    )

    benchmarks: dict[str, Any] = {
        "embedding": _benchmark_embedding(
            endpoint=resolved_endpoint,
            model=resolved_embedding_model,
            text="blood bonds, obfuscate, ritual timing, messy critical consequences",
        ),
        "answer": _benchmark_generation(
            endpoint=resolved_endpoint,
            model=resolved_answer_model,
            prompt=(
                "Answer in 2 concise, source-grounded sentences. "
                "What is a blood bond in Vampire: The Masquerade?"
            ),
        ),
        "process_memory": _ollama_process_memory(),
    }

    qa_data: dict[str, Any] | None = None
    created: list[str] = []
    if target is not None:
        from backet.bot_qa import run_bot_qa

        qa = run_bot_qa(
            target=target,
            case_files=case_files or [],
            command=command,
            user_id=user_id,
            role_ids=role_ids or [],
            private=True,
            limit=limit,
            use_model=True,
            report_output=report_output,
        )
        qa_data = qa.data
        created.extend(qa.created)

    data = {
        "ok": bool(benchmarks["embedding"].get("ok")) and bool(benchmarks["answer"].get("ok")) and (qa_data is None or qa_data.get("ok")),
        "doctor": doctor.data,
        "benchmarks": benchmarks,
        "qa": qa_data,
        "hardware_recommendation": _hardware_recommendation(doctor.data, benchmarks, qa_data),
    }
    if report_output is not None:
        created.extend(_write_benchmark_report(report_output.expanduser().resolve(), data))
    return CommandResult(
        message="Local RAG runtime benchmark complete",
        issues=doctor.issues,
        created=created,
        data=data,
    )


def ollama_embed(
    texts: list[str],
    *,
    model: str = DEFAULT_OLLAMA_EMBEDDING_MODEL,
    endpoint: str | None = None,
    timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    payload = {"model": model, "input": texts}
    return _post_json(_normalize_endpoint(endpoint) + "/api/embed", payload, timeout_seconds=timeout_seconds)


def ollama_generate(
    prompt: str,
    *,
    model: str = DEFAULT_OLLAMA_ANSWER_MODEL,
    endpoint: str | None = None,
    timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    token_budget: int = 512,
    stream: bool = False,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "options": {"temperature": 0.2, "num_predict": token_budget, "num_ctx": 2048},
    }
    if stream:
        return _post_json_stream(_normalize_endpoint(endpoint) + "/api/generate", payload, timeout_seconds=timeout_seconds)
    return _post_json(_normalize_endpoint(endpoint) + "/api/generate", payload, timeout_seconds=timeout_seconds)


def _ollama_status(*, endpoint: str, embedding_model: str, answer_model: str, model_cache: str) -> dict[str, Any]:
    command_path = _find_ollama_executable()
    status: dict[str, Any] = {
        "installed": command_path is not None,
        "command_path": command_path,
        "endpoint": endpoint,
        "api_available": False,
        "version": _ollama_version(command_path),
        "model_cache": model_cache,
        "models": [],
        "embedding_model": embedding_model,
        "answer_model": answer_model,
        "embedding_available": False,
        "answer_available": False,
        "backend_status": "unknown",
        "install_actions": [],
    }
    if command_path is None:
        status["install_actions"].append(_ollama_install_action(model_cache))
    try:
        tags = _get_json(endpoint + "/api/tags", timeout_seconds=5.0)
    except AppError as exc:
        status["api_error"] = exc.message
        status["install_actions"].append(_ollama_start_action(command_path, model_cache))
        return status

    models = [_model_summary(item) for item in tags.get("models", []) if isinstance(item, dict)]
    model_names = [str(item.get("name") or item.get("model") or "") for item in models]
    status.update(
        {
            "api_available": True,
            "models": models,
            "backend_status": "available",
            "embedding_available": _model_present(model_names, embedding_model),
            "answer_available": _model_present(model_names, answer_model),
        }
    )
    if not status["embedding_available"]:
        status["install_actions"].append(f"ollama pull {embedding_model}")
    if not status["answer_available"]:
        status["install_actions"].append(f"ollama pull {answer_model}")
    return status


def _llama_cpp_status() -> dict[str, Any]:
    command_path = _find_llama_cpp_executable()
    status = {
        "installed": command_path is not None,
        "command_path": command_path,
        "endpoint": LLAMA_CPP_ENDPOINT,
        "api_available": False,
        "install_actions": [],
    }
    if command_path is None:
        status["install_actions"].append(
            "Optional fallback: build llama.cpp with Vulkan and run `llama-server --host 127.0.0.1 --port 8080`."
        )
    try:
        _post_json(LLAMA_CPP_ENDPOINT, {"prompt": "ping", "n_predict": 1, "stream": False}, timeout_seconds=2.0)
    except AppError:
        return status
    status["api_available"] = True
    return status


def _profile_compatibility(
    *,
    ollama: dict[str, Any],
    config: dict[str, Any],
    profile: str,
    embedding_model: str,
    answer_model: str,
) -> dict[str, Any]:
    configured = parse_runtime_profile_config(config)
    services = configured.services
    embedding_available = bool(ollama.get("embedding_available")) or services[SERVICE_ROLE_EMBEDDING].configured
    answer_available = bool(ollama.get("answer_available")) or services[SERVICE_ROLE_ANSWER].configured
    reranker_available = services[SERVICE_ROLE_RERANKER].configured and bool(services[SERVICE_ROLE_RERANKER].endpoint)
    profiles = {
        RUNTIME_PROFILE_LITE: {"compatible": True, "missing_roles": [], "required_models": []},
        RUNTIME_PROFILE_RAG_STANDARD: {
            "compatible": embedding_available,
            "missing_roles": [] if embedding_available else [SERVICE_ROLE_EMBEDDING],
            "required_models": [embedding_model],
        },
        RUNTIME_PROFILE_RAG_QUALITY: {
            "compatible": embedding_available and answer_available and reranker_available,
            "missing_roles": [
                role
                for role, available in [
                    (SERVICE_ROLE_EMBEDDING, embedding_available),
                    (SERVICE_ROLE_RERANKER, reranker_available),
                    (SERVICE_ROLE_ANSWER, answer_available),
                ]
                if not available
            ],
            "required_models": [embedding_model, answer_model],
        },
    }
    return {
        "selected_profile": profile,
        "profiles": profiles,
        "service_roles": {
            SERVICE_ROLE_EMBEDDING: {"available": embedding_available, "model": embedding_model},
            SERVICE_ROLE_RERANKER: {"available": reranker_available, "model": services[SERVICE_ROLE_RERANKER].model},
            SERVICE_ROLE_ANSWER: {"available": answer_available, "model": answer_model},
        },
    }


def _benchmark_embedding(*, endpoint: str, model: str, text: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = ollama_embed([text], model=model, endpoint=endpoint, timeout_seconds=60.0)
    except AppError as exc:
        return {"ok": False, "model": model, "error": exc.code, "message": exc.message}
    elapsed = time.perf_counter() - started
    embeddings = result.get("embeddings") if isinstance(result, dict) else None
    first = embeddings[0] if isinstance(embeddings, list) and embeddings else []
    return {
        "ok": bool(first),
        "model": result.get("model") or model,
        "latency_seconds": round(elapsed, 4),
        "dimensions": len(first) if isinstance(first, list) else None,
        "total_duration_ns": result.get("total_duration"),
        "load_duration_ns": result.get("load_duration"),
    }


def _benchmark_generation(*, endpoint: str, model: str, prompt: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = ollama_generate(prompt, model=model, endpoint=endpoint, timeout_seconds=180.0, token_budget=160, stream=True)
    except AppError as exc:
        return {"ok": False, "model": model, "error": exc.code, "message": exc.message}
    elapsed = time.perf_counter() - started
    eval_count = int(result.get("eval_count") or 0)
    eval_duration = int(result.get("eval_duration") or 0)
    tokens_per_second = None
    if eval_count and eval_duration:
        tokens_per_second = round(eval_count / (eval_duration / 1_000_000_000), 2)
    return {
        "ok": bool(result.get("response")),
        "model": result.get("model") or model,
        "latency_seconds": round(elapsed, 4),
        "time_to_first_token_seconds": result.get("time_to_first_token_seconds"),
        "tokens_per_second": tokens_per_second,
        "eval_count": eval_count,
        "load_duration_ns": result.get("load_duration"),
        "response_chars": len(str(result.get("response") or "")),
        "response_preview": str(result.get("response") or "")[:280],
    }


def _hardware_recommendation(doctor: dict[str, Any], benchmarks: dict[str, Any], qa_data: dict[str, Any] | None) -> dict[str, Any]:
    quality = dict(dict(doctor.get("profile_compatibility", {}) or {}).get("profiles", {}) or {}).get(
        RUNTIME_PROFILE_RAG_QUALITY,
        {},
    )
    standard = dict(dict(doctor.get("profile_compatibility", {}) or {}).get("profiles", {}) or {}).get(
        RUNTIME_PROFILE_RAG_STANDARD,
        {},
    )
    answer = dict(benchmarks.get("answer", {}) or {})
    if qa_data is not None and not qa_data.get("ok"):
        status = "quality_gap"
        summary = "Model services ran, but the QA suite did not pass; improve retrieval/synthesis before sizing production."
    elif answer.get("ok") and standard.get("compatible") and quality.get("compatible"):
        status = "quality_profile_candidate"
        summary = "This machine can be used as the first quality-profile sizing reference."
    elif answer.get("ok") and standard.get("compatible"):
        status = "standard_profile_ready"
        summary = "Local embedding and answer generation work, but rag-quality still needs a reranker service."
    else:
        status = "runtime_not_ready"
        summary = "Local runtime is not yet ready for production sizing."
    return {
        "status": status,
        "summary": summary,
        "minimum_practical_host": "For rag-standard, start from 32 GB RAM, fast SSD cache, and GPU/runtime compatibility matching this machine.",
        "quality_gap": {
            "missing_roles": quality.get("missing_roles", []),
            "qa_ok": None if qa_data is None else bool(qa_data.get("ok")),
        },
    }


def _runtime_issues(ollama: dict[str, Any], llama_cpp: dict[str, Any], compatibility: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    if not ollama.get("installed"):
        issues.append(
            Issue(
                code="local_runtime_ollama_missing",
                severity="warning",
                message="Ollama is not installed or not on a known local path.",
                hint=str(ollama.get("install_actions", ["Install Ollama."])[0]),
                safe_to_fix=False,
            )
        )
    if ollama.get("installed") and not ollama.get("api_available"):
        issues.append(
            Issue(
                code="local_runtime_ollama_api_unavailable",
                severity="warning",
                message="Ollama is installed but its local API is not reachable.",
                hint="Start Ollama and rerun `backet bot runtime doctor`.",
                safe_to_fix=False,
            )
        )
    if ollama.get("api_available") and not ollama.get("embedding_available"):
        issues.append(
            Issue(
                code="local_runtime_embedding_model_missing",
                severity="warning",
                message="The configured Ollama embedding model is not pulled.",
                hint=f"Run `ollama pull {ollama.get('embedding_model')}`.",
                safe_to_fix=False,
            )
        )
    if ollama.get("api_available") and not ollama.get("answer_available"):
        issues.append(
            Issue(
                code="local_runtime_answer_model_missing",
                severity="warning",
                message="The configured Ollama answer model is not pulled.",
                hint=f"Run `ollama pull {ollama.get('answer_model')}`.",
                safe_to_fix=False,
            )
        )
    quality = compatibility["profiles"][RUNTIME_PROFILE_RAG_QUALITY]
    if quality.get("missing_roles"):
        issues.append(
            Issue(
                code="local_runtime_quality_profile_incomplete",
                severity="warning",
                message="The local runtime is not compatible with rag-quality yet.",
                hint=f"Missing roles: {', '.join(quality.get('missing_roles', []))}.",
                safe_to_fix=False,
            )
        )
    if not llama_cpp.get("installed"):
        issues.append(
            Issue(
                code="local_runtime_llama_cpp_fallback_missing",
                severity="info",
                message="llama.cpp Vulkan fallback is not installed.",
                hint="This is optional while Ollama is available.",
                safe_to_fix=False,
            )
        )
    return issues


def _hardware_inventory() -> dict[str, Any]:
    hardware: dict[str, Any] = {"cpu": platform.processor() or platform.machine(), "logical_cpus": os.cpu_count()}
    if platform.system().lower() != "windows":
        return hardware
    hardware.update(_windows_cim_inventory())
    return hardware


def _windows_cim_inventory() -> dict[str, Any]:
    script = (
        "$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1 Name,NumberOfCores,NumberOfLogicalProcessors; "
        "$system=Get-CimInstance Win32_ComputerSystem | Select-Object -First 1 TotalPhysicalMemory,Manufacturer,Model; "
        "$gpu=Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion; "
        "[pscustomobject]@{cpu=$cpu;system=$system;gpu=$gpu} | ConvertTo-Json -Depth 6"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if completed.returncode != 0 or not completed.stdout.strip():
        return {}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {}
    gpus = payload.get("gpu", [])
    if isinstance(gpus, dict):
        gpus = [gpus]
    return {
        "cpu": payload.get("cpu", {}),
        "system": payload.get("system", {}),
        "gpus": gpus,
        "amd_gpus": [gpu for gpu in gpus if "amd" in str(gpu.get("Name", "")).casefold()],
    }


def _find_ollama_executable() -> str | None:
    candidates = [
        os.environ.get("BACKET_OLLAMA_EXE"),
        shutil.which("ollama"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"),
        "H:/Tools/Ollama/ollama.exe",
        "C:/Program Files/Ollama/ollama.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    return None


def _find_llama_cpp_executable() -> str | None:
    for name in ("llama-server", "llama-server.exe", "server.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _ollama_version(command_path: str | None) -> str | None:
    if not command_path:
        return None
    try:
        completed = subprocess.run([command_path, "--version"], text=True, capture_output=True, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _get_json(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise AppError(
            code="local_runtime_http_unavailable",
            message="Local model runtime API is unavailable or returned invalid JSON.",
            hint=f"Check {url}.",
            details={"url": url, "error": str(exc)},
            exit_code=2,
        ) from exc


def _post_json(url: str, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AppError(
            code="local_runtime_http_error",
            message="Local model runtime rejected the request.",
            hint=body[:500] or str(exc),
            details={"url": url, "status": exc.code, "body": body[:1000]},
            exit_code=2,
        ) from exc
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise AppError(
            code="local_runtime_http_unavailable",
            message="Local model runtime API is unavailable or returned invalid JSON.",
            hint=f"Check {url}.",
            details={"url": url, "error": str(exc)},
            exit_code=2,
        ) from exc


def _post_json_stream(url: str, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
        method="POST",
    )
    started = time.perf_counter()
    first_token_at: float | None = None
    response_text: list[str] = []
    final: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                item = json.loads(raw_line.decode("utf-8"))
                token = str(item.get("response") or "")
                if token and first_token_at is None:
                    first_token_at = time.perf_counter()
                response_text.append(token)
                if item.get("done"):
                    final = item
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AppError(
            code="local_runtime_http_error",
            message="Local model runtime rejected the request.",
            hint=body[:500] or str(exc),
            details={"url": url, "status": exc.code, "body": body[:1000]},
            exit_code=2,
        ) from exc
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise AppError(
            code="local_runtime_http_unavailable",
            message="Local model runtime API is unavailable or returned invalid JSON.",
            hint=f"Check {url}.",
            details={"url": url, "error": str(exc)},
            exit_code=2,
        ) from exc
    final["response"] = "".join(response_text)
    if first_token_at is not None:
        final["time_to_first_token_seconds"] = round(first_token_at - started, 4)
    return final


def _model_summary(item: dict[str, Any]) -> dict[str, Any]:
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    return {
        "name": item.get("name") or item.get("model"),
        "model": item.get("model") or item.get("name"),
        "size": item.get("size"),
        "digest": item.get("digest"),
        "modified_at": item.get("modified_at"),
        "family": details.get("family"),
        "parameter_size": details.get("parameter_size"),
        "quantization_level": details.get("quantization_level"),
    }


def _model_present(model_names: list[str], requested: str) -> bool:
    requested = requested.strip()
    aliases = {requested, requested.removesuffix(":latest"), f"{requested}:latest"}
    return any(name in aliases or name.split(":", 1)[0] == requested for name in model_names)


def _configured_model(config: dict[str, Any] | None, role: str) -> str | None:
    if not config:
        return None
    services = dict(config.get("model_services", {}) or {})
    service = services.get(role)
    if isinstance(service, dict) and service.get("model"):
        return str(service["model"])
    if role == SERVICE_ROLE_ANSWER and isinstance(config.get("model"), dict):
        model = dict(config.get("model") or {})
        if model.get("name") or model.get("model"):
            return str(model.get("name") or model.get("model"))
    return None


def _normalize_endpoint(endpoint: str | None) -> str:
    return str(endpoint or os.environ.get("BACKET_OLLAMA_ENDPOINT") or DEFAULT_OLLAMA_ENDPOINT).rstrip("/")


def _default_model_cache_path() -> str:
    if platform.system().lower() == "windows":
        return DEFAULT_MODEL_CACHE_WINDOWS
    return str(Path.home() / ".ollama" / "models")


def _ollama_install_action(model_cache: str) -> str:
    if platform.system().lower() == "windows":
        return f"winget install --id Ollama.Ollama --exact --location H:\\Tools\\Ollama; set OLLAMA_MODELS={model_cache}"
    return "Install Ollama from https://ollama.com/download and set OLLAMA_MODELS to an operator-controlled model cache."


def _ollama_start_action(command_path: str | None, model_cache: str) -> str:
    executable = command_path or "ollama"
    return f"Set OLLAMA_MODELS={model_cache} and run `{executable} serve`."


def _ollama_process_memory() -> dict[str, Any]:
    if platform.system().lower() != "windows":
        return {"available": False}
    script = (
        "Get-Process | Where-Object { $_.ProcessName -like 'ollama*' } | "
        "Select-Object ProcessName,Id,WorkingSet64,PeakWorkingSet64 | ConvertTo-Json -Depth 4"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False}
    if completed.returncode != 0 or not completed.stdout.strip():
        return {"available": False}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"available": False}
    processes = payload if isinstance(payload, list) else [payload]
    return {
        "available": True,
        "processes": processes,
        "working_set_bytes": sum(int(item.get("WorkingSet64") or 0) for item in processes if isinstance(item, dict)),
        "peak_working_set_bytes": max([int(item.get("PeakWorkingSet64") or 0) for item in processes if isinstance(item, dict)] or [0]),
    }


def _write_benchmark_report(output: Path, data: dict[str, Any]) -> list[str]:
    if output.suffix.lower() == ".json":
        json_path = output
        markdown_path = output.with_suffix(".md")
    else:
        output.mkdir(parents=True, exist_ok=True)
        json_path = output / "local-runtime-benchmark.json"
        markdown_path = output / "local-runtime-benchmark.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_benchmark_markdown(data), encoding="utf-8")
    return [str(json_path), str(markdown_path)]


def _benchmark_markdown(data: dict[str, Any]) -> str:
    answer = dict(dict(data.get("benchmarks", {}) or {}).get("answer", {}) or {})
    embedding = dict(dict(data.get("benchmarks", {}) or {}).get("embedding", {}) or {})
    recommendation = dict(data.get("hardware_recommendation", {}) or {})
    lines = [
        "# Local RAG Runtime Benchmark",
        "",
        f"- Overall: {'ok' if data.get('ok') else 'needs action'}",
        f"- Embedding: {embedding.get('model')} ({embedding.get('latency_seconds')}s, {embedding.get('dimensions')} dims)",
        f"- Answer: {answer.get('model')} ({answer.get('latency_seconds')}s, {answer.get('tokens_per_second')} tok/s)",
        f"- Recommendation: {recommendation.get('status')}",
        "",
        str(recommendation.get("summary") or ""),
        "",
    ]
    return "\n".join(lines)
