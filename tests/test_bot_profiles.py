from __future__ import annotations

import json

from backet.bot_profiles import (
    doctor_runtime_profile,
    issues_from_runtime_health,
    parse_runtime_profile_config,
    runtime_profile_manifest,
)


def test_runtime_profile_defaults_to_lite_without_required_services() -> None:
    profile = parse_runtime_profile_config({})
    manifest = runtime_profile_manifest({})

    assert profile.profile == "lite"
    assert profile.fallback_policy == "template"
    assert all(not service.required for service in profile.services.values())
    assert manifest["profile"] == "lite"
    assert manifest["model_files_bundled"] is False
    assert manifest["services"]["embedding"]["required"] is False


def test_runtime_profile_manifest_records_non_secret_service_metadata() -> None:
    manifest = runtime_profile_manifest(
        {
            "runtime_profile": "rag-quality",
            "model_services": {
                "embedding": {
                    "provider": "self-hosted",
                    "endpoint": "http://embedding:8080/embed",
                    "model": "bge-small",
                    "dimensions": 384,
                    "api_key_env": "BACKET_EMBEDDING_API_KEY",
                    "token": "never-write-this",
                    "compatibility": {"api_key": "also-never", "format": "float32"},
                },
                "reranker": {"provider": "self-hosted", "endpoint": "http://reranker:8080/rerank", "model": "bge-reranker"},
                "answer": {"provider": "local", "endpoint": "http://llama:8080/completion", "model": "llama-3.1-8b"},
            },
        }
    )

    serialized = json.dumps(manifest, sort_keys=True)
    assert manifest["profile"] == "rag-quality"
    assert manifest["services"]["embedding"]["required"] is True
    assert manifest["services"]["embedding"]["model"] == "bge-small"
    assert manifest["services"]["embedding"]["dimensions"] == 384
    assert "never-write-this" not in serialized
    assert "BACKET_EMBEDDING_API_KEY" not in serialized
    assert "also-never" not in serialized


def test_runtime_doctor_reports_healthy_degraded_and_missing_services() -> None:
    healthy = doctor_runtime_profile(
        {
            "runtime_profile": "rag-standard",
            "model_services": {
                "embedding": {
                    "provider": "self-hosted",
                    "endpoint": "http://embedding:8080/embed",
                    "model": "bge-small",
                    "dimensions": 384,
                    "timeout_seconds": 1,
                }
            },
        },
        service_checkers={
            "embedding": lambda service: {
                "ok": True,
                "model": service.model,
                "dimensions": 384,
                "elapsed_seconds": 0.05,
            }
        },
    )
    degraded = doctor_runtime_profile({"runtime_profile": "rag-standard"})
    fail_closed = doctor_runtime_profile({"runtime_profile": "rag-quality"})

    assert healthy["ok"] is True
    assert healthy["degraded"] is False
    assert healthy["services"]["embedding"]["status"] == "healthy"
    assert degraded["ok"] is True
    assert degraded["degraded"] is True
    assert degraded["services"]["embedding"]["status"] == "missing"
    assert degraded["services"]["embedding"]["severity"] == "warning"
    assert fail_closed["ok"] is False
    assert fail_closed["fail_closed"] is True
    assert fail_closed["services"]["answer"]["severity"] == "error"


def test_runtime_doctor_rejects_third_party_hosted_model_apis() -> None:
    health = doctor_runtime_profile(
        {
            "runtime_profile": "rag-standard",
            "model_services": {
                "embedding": {
                    "provider": "openai",
                    "endpoint": "https://api.openai.com/v1/embeddings",
                    "model": "text-embedding-3-large",
                    "dimensions": 3072,
                }
            },
        }
    )
    issues = issues_from_runtime_health(health)

    assert health["ok"] is False
    assert health["services"]["embedding"]["status"] == "unsupported"
    assert issues[0].code == "bot_runtime_service_embedding_unsupported"


def test_runtime_profile_imports_ollama_answer_mode_as_answer_service() -> None:
    profile = parse_runtime_profile_config(
        {
            "runtime_profile": "rag-standard",
            "answer_mode": "ollama-local",
            "model": {"model": "llama3.2:3b", "endpoint": "http://127.0.0.1:11434"},
            "model_services": {
                "embedding": {"provider": "ollama", "endpoint": "http://127.0.0.1:11434", "model": "nomic-embed-text"}
            },
        }
    )

    assert profile.services["answer"].provider == "ollama"
    assert profile.services["answer"].model == "llama3.2:3b"
