from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

from backet.errors import AppError
from backet.models import Issue

RUNTIME_PROFILE_LITE = "lite"
RUNTIME_PROFILE_RAG_STANDARD = "rag-standard"
RUNTIME_PROFILE_RAG_QUALITY = "rag-quality"
RUNTIME_PROFILES = {RUNTIME_PROFILE_LITE, RUNTIME_PROFILE_RAG_STANDARD, RUNTIME_PROFILE_RAG_QUALITY}

FALLBACK_TEMPLATE = "template"
FALLBACK_DEGRADE = "degrade"
FALLBACK_FAIL_CLOSED = "fail-closed"
FALLBACK_POLICIES = {FALLBACK_TEMPLATE, FALLBACK_DEGRADE, FALLBACK_FAIL_CLOSED}

SERVICE_ROLE_EMBEDDING = "embedding"
SERVICE_ROLE_RERANKER = "reranker"
SERVICE_ROLE_ANSWER = "answer"
MODEL_SERVICE_ROLES = (SERVICE_ROLE_EMBEDDING, SERVICE_ROLE_RERANKER, SERVICE_ROLE_ANSWER)

DEFAULT_SERVICE_TIMEOUTS = {
    SERVICE_ROLE_EMBEDDING: 5.0,
    SERVICE_ROLE_RERANKER: 5.0,
    SERVICE_ROLE_ANSWER: 20.0,
}
DEFAULT_ENDPOINT_ENV = {
    SERVICE_ROLE_EMBEDDING: "BACKET_EMBEDDING_ENDPOINT",
    SERVICE_ROLE_RERANKER: "BACKET_RERANKER_ENDPOINT",
    SERVICE_ROLE_ANSWER: "BACKET_ANSWER_MODEL_ENDPOINT",
}

UNSUPPORTED_PROVIDER_NAMES = {
    "anthropic",
    "azure",
    "cohere",
    "gemini",
    "google",
    "huggingface-api",
    "mistral",
    "openai",
    "openrouter",
    "third-party",
    "together",
}
UNSUPPORTED_ENDPOINT_HOSTS = {
    "api.anthropic.com",
    "api.cohere.ai",
    "api.fireworks.ai",
    "api.groq.com",
    "api.mistral.ai",
    "api.openai.com",
    "api.openrouter.ai",
    "api.together.xyz",
    "generativelanguage.googleapis.com",
}
SECRET_FIELD_MARKERS = ("api_key", "apikey", "authorization", "bearer", "password", "private_key", "secret", "token")


@dataclass(frozen=True, slots=True)
class RuntimeProfileDefinition:
    profile: str
    fallback_policy: str
    required_roles: tuple[str, ...]
    optional_roles: tuple[str, ...]
    degraded_allowed: bool
    fail_closed: bool


PROFILE_DEFINITIONS = {
    RUNTIME_PROFILE_LITE: RuntimeProfileDefinition(
        profile=RUNTIME_PROFILE_LITE,
        fallback_policy=FALLBACK_TEMPLATE,
        required_roles=(),
        optional_roles=(SERVICE_ROLE_EMBEDDING, SERVICE_ROLE_RERANKER, SERVICE_ROLE_ANSWER),
        degraded_allowed=True,
        fail_closed=False,
    ),
    RUNTIME_PROFILE_RAG_STANDARD: RuntimeProfileDefinition(
        profile=RUNTIME_PROFILE_RAG_STANDARD,
        fallback_policy=FALLBACK_DEGRADE,
        required_roles=(SERVICE_ROLE_EMBEDDING,),
        optional_roles=(SERVICE_ROLE_RERANKER, SERVICE_ROLE_ANSWER),
        degraded_allowed=True,
        fail_closed=False,
    ),
    RUNTIME_PROFILE_RAG_QUALITY: RuntimeProfileDefinition(
        profile=RUNTIME_PROFILE_RAG_QUALITY,
        fallback_policy=FALLBACK_FAIL_CLOSED,
        required_roles=(SERVICE_ROLE_EMBEDDING, SERVICE_ROLE_RERANKER, SERVICE_ROLE_ANSWER),
        optional_roles=(),
        degraded_allowed=False,
        fail_closed=True,
    ),
}


@dataclass(slots=True)
class ModelServiceConfig:
    role: str
    provider: str = "disabled"
    endpoint: str | None = None
    endpoint_env: str | None = None
    model: str | None = None
    dimensions: int | None = None
    timeout_seconds: float = 5.0
    required: bool = False
    enabled: bool = False
    local_model_path: str | None = None
    compatibility: dict[str, Any] = field(default_factory=dict)
    unsupported_reason: str | None = None

    @property
    def configured(self) -> bool:
        if self.provider == "disabled":
            return False
        return self.enabled or any([self.endpoint, self.model, self.dimensions, self.local_model_path])

    def to_config(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "required": self.required,
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
            "endpoint_env": self.endpoint_env or DEFAULT_ENDPOINT_ENV[self.role],
        }
        if self.endpoint:
            payload["endpoint"] = self.endpoint
        if self.model:
            payload["model"] = self.model
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions
        if self.local_model_path:
            payload["local_model_path"] = self.local_model_path
        if self.compatibility:
            payload["compatibility"] = scrub_secret_fields(self.compatibility)
        if self.unsupported_reason:
            payload["unsupported_reason"] = self.unsupported_reason
        return payload

    def to_manifest(self) -> dict[str, Any]:
        payload = self.to_config()
        payload.update(
            {
                "role": self.role,
                "configured": self.configured,
                "endpoint_role": self.endpoint_env or DEFAULT_ENDPOINT_ENV[self.role],
            }
        )
        return scrub_secret_fields(payload)


@dataclass(slots=True)
class RuntimeProfileConfig:
    profile: str
    fallback_policy: str
    services: dict[str, ModelServiceConfig]
    degraded_allowed: bool
    fail_closed: bool

    def to_config(self) -> dict[str, Any]:
        configured_services = {
            role: service.to_config()
            for role, service in self.services.items()
            if service.configured or service.required
        }
        return {
            "runtime_profile": self.profile,
            "fallback_policy": self.fallback_policy,
            "model_services": configured_services,
        }

    def to_manifest(self, *, indexes: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "profile": self.profile,
            "fallback_policy": self.fallback_policy,
            "degraded_allowed": self.degraded_allowed,
            "fail_closed": self.fail_closed,
            "model_files_bundled": False,
            "services": {role: self.services[role].to_manifest() for role in MODEL_SERVICE_ROLES},
            "compatibility": {
                "indexes": _index_compatibility(indexes or {}),
            },
        }


ServiceChecker = Callable[[ModelServiceConfig], dict[str, Any] | bool | None]


def normalize_runtime_profile(value: Any) -> str:
    profile = str(value or RUNTIME_PROFILE_LITE).strip().lower().replace("_", "-")
    if profile in {"standard", "rag"}:
        profile = RUNTIME_PROFILE_RAG_STANDARD
    if profile in {"quality", "rag-v2", "rag-v2-quality"}:
        profile = RUNTIME_PROFILE_RAG_QUALITY
    if profile not in RUNTIME_PROFILES:
        raise AppError(
            code="bot_runtime_profile_invalid",
            message="Bot runtime profile is invalid.",
            hint=f"Use one of: {', '.join(sorted(RUNTIME_PROFILES))}.",
            details={"runtime_profile": value},
            exit_code=2,
        )
    return profile


def normalize_fallback_policy(value: Any, *, default: str) -> str:
    policy = str(value or default).strip().lower().replace("_", "-")
    if policy in {"failclosed", "fail"}:
        policy = FALLBACK_FAIL_CLOSED
    if policy not in FALLBACK_POLICIES:
        raise AppError(
            code="bot_runtime_fallback_policy_invalid",
            message="Bot runtime fallback policy is invalid.",
            hint=f"Use one of: {', '.join(sorted(FALLBACK_POLICIES))}.",
            details={"fallback_policy": value},
            exit_code=2,
        )
    return policy


def parse_runtime_profile_config(config: dict[str, Any] | None) -> RuntimeProfileConfig:
    config = dict(config or {})
    runtime = _mapping(config.get("runtime"), field_name="runtime", default={})
    profile = normalize_runtime_profile(
        config.get("runtime_profile")
        or config.get("profile")
        or runtime.get("profile")
        or runtime.get("runtime_profile")
        or RUNTIME_PROFILE_LITE
    )
    definition = PROFILE_DEFINITIONS[profile]
    fallback_policy = normalize_fallback_policy(
        config.get("fallback_policy") or runtime.get("fallback_policy"),
        default=definition.fallback_policy,
    )
    fail_closed = fallback_policy == FALLBACK_FAIL_CLOSED or definition.fail_closed
    degraded_allowed = fallback_policy != FALLBACK_FAIL_CLOSED and definition.degraded_allowed
    raw_services = _mapping(
        config.get("model_services") or runtime.get("model_services"),
        field_name="model_services",
        default={},
    )
    raw_services = _normalize_service_keys(raw_services)
    answer_mode = str(config.get("answer_mode") or "").strip()
    model = _mapping(config.get("model"), field_name="model", default={})
    if answer_mode == "llama-local" and SERVICE_ROLE_ANSWER not in raw_services:
        raw_services[SERVICE_ROLE_ANSWER] = _legacy_llama_answer_service(model)

    services = {}
    for role in MODEL_SERVICE_ROLES:
        raw = _mapping(raw_services.get(role), field_name=f"model_services.{role}", default={})
        required = role in definition.required_roles or bool(raw.get("required", False))
        services[role] = _parse_service(role, raw, required=required)
    return RuntimeProfileConfig(
        profile=profile,
        fallback_policy=fallback_policy,
        services=services,
        degraded_allowed=degraded_allowed,
        fail_closed=fail_closed,
    )


def runtime_profile_manifest(config: dict[str, Any] | None, *, indexes: dict[str, Any] | None = None) -> dict[str, Any]:
    return parse_runtime_profile_config(config).to_manifest(indexes=indexes)


def runtime_profile_from_manifest(manifest: dict[str, Any]) -> RuntimeProfileConfig:
    runtime = manifest.get("runtime")
    if isinstance(runtime, dict) and runtime.get("profile"):
        return parse_runtime_profile_config(
            {
                "runtime_profile": runtime.get("profile"),
                "fallback_policy": runtime.get("fallback_policy"),
                "model_services": runtime.get("services", {}),
            }
        )
    return parse_runtime_profile_config(manifest.get("bot", {}))


def doctor_runtime_profile(
    config: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
    service_checkers: dict[str, ServiceChecker] | None = None,
) -> dict[str, Any]:
    profile = runtime_profile_from_manifest(config) if "runtime" in config else parse_runtime_profile_config(config)
    service_checkers = service_checkers or {}
    services = {
        role: _doctor_service(profile.services[role], profile=profile, manifest=manifest or config, checker=service_checkers.get(role))
        for role in MODEL_SERVICE_ROLES
    }
    degraded = any(bool(service.get("degrades_runtime")) for service in services.values())
    error_count = sum(1 for service in services.values() if service.get("severity") == "error")
    return {
        "profile": profile.profile,
        "fallback_policy": profile.fallback_policy,
        "degraded_allowed": profile.degraded_allowed,
        "fail_closed": profile.fail_closed,
        "degraded": degraded,
        "ok": error_count == 0,
        "services": services,
        "blocking": error_count > 0,
    }


def issues_from_runtime_health(health: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    for role, service in dict(health.get("services", {}) or {}).items():
        severity = service.get("severity")
        if severity not in {"warning", "error"}:
            continue
        status = str(service.get("status") or "unknown").replace("-", "_")
        message = service.get("message") or f"Runtime service {role} is {status}."
        hint = service.get("hint") or "Check bot runtime profile and model service configuration."
        issues.append(
            Issue(
                code=f"bot_runtime_service_{role}_{status}",
                severity=str(severity),
                message=str(message),
                hint=str(hint),
                safe_to_fix=False,
            )
        )
    return issues


def scrub_secret_fields(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower().replace("-", "_")
            if _is_secret_field(lowered):
                continue
            scrubbed[key_text] = scrub_secret_fields(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub_secret_fields(item) for item in value]
    if isinstance(value, tuple):
        return [scrub_secret_fields(item) for item in value]
    return value


def _parse_service(role: str, raw: dict[str, Any], *, required: bool) -> ModelServiceConfig:
    endpoint = _optional_string(raw.get("endpoint") or raw.get("url") or raw.get("base_url"))
    endpoint_env = _optional_string(raw.get("endpoint_env") or raw.get("endpoint_role") or DEFAULT_ENDPOINT_ENV[role])
    model = _optional_string(raw.get("model") or raw.get("model_id") or raw.get("name"))
    local_model_path = _optional_string(raw.get("local_model_path") or raw.get("model_path") or raw.get("path"))
    provider = _normalize_provider(raw.get("provider") or raw.get("backend"), endpoint=endpoint, model=model, local_model_path=local_model_path)
    dimensions = _optional_int(raw.get("dimensions") or raw.get("embedding_dimensions"))
    timeout_seconds = _optional_float(raw.get("timeout_seconds") or raw.get("timeout"), DEFAULT_SERVICE_TIMEOUTS[role])
    compatibility = _mapping(raw.get("compatibility"), field_name=f"model_services.{role}.compatibility", default={})
    unsupported_reason = _unsupported_reason(provider=provider, endpoint=endpoint)
    enabled = bool(raw.get("enabled", provider != "disabled" and any([endpoint, model, dimensions, local_model_path])))
    return ModelServiceConfig(
        role=role,
        provider=provider,
        endpoint=endpoint,
        endpoint_env=endpoint_env,
        model=model,
        dimensions=dimensions,
        timeout_seconds=timeout_seconds,
        required=required,
        enabled=enabled,
        local_model_path=local_model_path,
        compatibility=scrub_secret_fields(compatibility),
        unsupported_reason=unsupported_reason,
    )


def _doctor_service(
    service: ModelServiceConfig,
    *,
    profile: RuntimeProfileConfig,
    manifest: dict[str, Any],
    checker: ServiceChecker | None,
) -> dict[str, Any]:
    base = {
        "role": service.role,
        "required": service.required,
        "configured": service.configured,
        "provider": service.provider,
        "endpoint": service.endpoint,
        "endpoint_role": service.endpoint_env or DEFAULT_ENDPOINT_ENV[service.role],
        "model": service.model,
        "dimensions": service.dimensions,
        "timeout_seconds": service.timeout_seconds,
    }
    if service.unsupported_reason:
        return {
            **base,
            "status": "unsupported",
            "severity": "error",
            "message": f"{service.role} model service uses an unsupported hosted provider.",
            "hint": service.unsupported_reason,
            "degrades_runtime": True,
        }
    if not service.configured:
        return _missing_service_health(service, profile=profile, base=base)
    if checker is None:
        return _unchecked_service_health(service, manifest=manifest, base=base)
    try:
        raw_result = checker(service)
    except Exception as exc:
        return _failed_service_health(
            service,
            profile=profile,
            base=base,
            status="unavailable",
            message=f"{service.role} model service check failed.",
            hint=str(exc),
        )
    result = _normalize_checker_result(raw_result)
    if result.get("elapsed_seconds") is not None and float(result["elapsed_seconds"]) > service.timeout_seconds:
        return _failed_service_health(
            service,
            profile=profile,
            base={**base, **result},
            status="timeout",
            message=f"{service.role} model service exceeded its configured timeout.",
            hint=f"Expected <= {service.timeout_seconds}s, got {result['elapsed_seconds']}s.",
        )
    if service.dimensions is not None and result.get("dimensions") is not None and int(result["dimensions"]) != service.dimensions:
        return _failed_service_health(
            service,
            profile=profile,
            base={**base, **result},
            status="incompatible",
            message=f"{service.role} model service returned incompatible dimensions.",
            hint=f"Expected {service.dimensions}, got {result['dimensions']}.",
        )
    if not result.get("ok", False):
        return _failed_service_health(
            service,
            profile=profile,
            base={**base, **result},
            status=str(result.get("status") or "unavailable"),
            message=str(result.get("message") or f"{service.role} model service is unavailable."),
            hint=str(result.get("hint") or "Check the service endpoint and timeout."),
        )
    return {
        **base,
        **result,
        "status": "healthy",
        "severity": "info",
        "message": f"{service.role} model service is healthy.",
        "degrades_runtime": False,
    }


def _missing_service_health(service: ModelServiceConfig, *, profile: RuntimeProfileConfig, base: dict[str, Any]) -> dict[str, Any]:
    if not service.required:
        return {
            **base,
            "status": "not_required",
            "severity": "info",
            "message": f"{service.role} model service is not required for the {profile.profile} profile.",
            "degrades_runtime": False,
        }
    severity = "error" if profile.fail_closed else "warning"
    return {
        **base,
        "status": "missing",
        "severity": severity,
        "message": f"{profile.profile} requires a configured {service.role} model service.",
        "hint": "Configure a local or self-hosted model service, or choose the lite profile.",
        "degrades_runtime": True,
    }


def _unchecked_service_health(service: ModelServiceConfig, *, manifest: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    if service.role == SERVICE_ROLE_EMBEDDING:
        index_compat = _index_compatibility(dict(manifest.get("indexes", {}) or {}))
        non_hash = [
            meta
            for meta in index_compat.values()
            if isinstance(meta, dict) and meta.get("embedding_backend") not in (None, "", "hash")
        ]
        if non_hash and service.provider in {"local", "builtin"}:
            return {
                **base,
                "status": "healthy",
                "severity": "info",
                "message": "Embedding compatibility metadata is available from bundled indexes.",
                "compatibility": {"indexes": index_compat},
                "degrades_runtime": False,
            }
    return {
        **base,
        "status": "not_checked",
        "severity": "info",
        "message": f"{service.role} model service is configured; live endpoint probing was not requested.",
        "hint": "Run startup/runtime checks from the host that can reach the service endpoint.",
        "degrades_runtime": False,
    }


def _failed_service_health(
    service: ModelServiceConfig,
    *,
    profile: RuntimeProfileConfig,
    base: dict[str, Any],
    status: str,
    message: str,
    hint: str,
) -> dict[str, Any]:
    severity = "error" if service.required and profile.fail_closed else "warning"
    return {
        **base,
        "status": status,
        "severity": severity,
        "message": message,
        "hint": hint,
        "degrades_runtime": True,
    }


def _normalize_checker_result(raw_result: dict[str, Any] | bool | None) -> dict[str, Any]:
    if raw_result is True:
        return {"ok": True}
    if raw_result in (False, None):
        return {"ok": False, "status": "unavailable"}
    result = dict(raw_result)
    if "ok" not in result:
        result["ok"] = str(result.get("status") or "").lower() in {"healthy", "ok", "ready"}
    return result


def _normalize_service_keys(raw_services: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "answer-model": SERVICE_ROLE_ANSWER,
        "answer_model": SERVICE_ROLE_ANSWER,
        "completion": SERVICE_ROLE_ANSWER,
        "llm": SERVICE_ROLE_ANSWER,
        "semantic": SERVICE_ROLE_EMBEDDING,
        "semantic-retrieval": SERVICE_ROLE_EMBEDDING,
        "semantic_retrieval": SERVICE_ROLE_EMBEDDING,
    }
    normalized: dict[str, Any] = {}
    for key, value in raw_services.items():
        role = str(key).strip().lower().replace("_", "-")
        role = aliases.get(role, role)
        if role not in MODEL_SERVICE_ROLES:
            raise AppError(
                code="bot_model_service_role_invalid",
                message="Bot model service role is invalid.",
                hint=f"Use one of: {', '.join(MODEL_SERVICE_ROLES)}.",
                details={"role": key},
                exit_code=2,
            )
        normalized[role] = value
    return normalized


def _legacy_llama_answer_service(model: dict[str, Any]) -> dict[str, Any]:
    path = _optional_string(model.get("path") or model.get("model_path"))
    return {
        "provider": "local",
        "endpoint": model.get("endpoint"),
        "endpoint_env": "BACKET_LLAMA_ENDPOINT",
        "model": model.get("name") or model.get("model") or (path.split("/")[-2] if path and "/" in path else path),
        "local_model_path": path,
        "timeout_seconds": model.get("timeout_seconds") or model.get("timeout") or DEFAULT_SERVICE_TIMEOUTS[SERVICE_ROLE_ANSWER],
        "enabled": True,
    }


def _normalize_provider(value: Any, *, endpoint: str | None, model: str | None, local_model_path: str | None) -> str:
    provider = str(value or "").strip().lower().replace("_", "-")
    if not provider:
        provider = "self-hosted" if endpoint else ("local" if model or local_model_path else "disabled")
    if provider in {"none", "off", "false"}:
        provider = "disabled"
    return provider


def _unsupported_reason(*, provider: str, endpoint: str | None) -> str | None:
    if provider in UNSUPPORTED_PROVIDER_NAMES:
        return "Third-party hosted model APIs are not supported by this initial hosting profile slice."
    host = _endpoint_host(endpoint)
    if host in UNSUPPORTED_ENDPOINT_HOSTS:
        return f"Endpoint host {host} is a third-party hosted model API and is unsupported here."
    return None


def _endpoint_host(endpoint: str | None) -> str | None:
    if not endpoint:
        return None
    parsed = urlparse(endpoint)
    return (parsed.hostname or "").strip().lower() or None


def _index_compatibility(indexes: dict[str, Any]) -> dict[str, Any]:
    compatibility: dict[str, Any] = {}
    for scope, meta in indexes.items():
        if not isinstance(meta, dict):
            continue
        compatibility[str(scope)] = {
            "embedding_backend": meta.get("embedding_backend"),
            "embedding_model": meta.get("embedding_model"),
        }
        if meta.get("embedding_dimensions") is not None:
            compatibility[str(scope)]["embedding_dimensions"] = meta.get("embedding_dimensions")
    return compatibility


def _mapping(value: Any, *, field_name: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if value in (None, ""):
        return dict(default or {})
    if not isinstance(value, dict):
        raise AppError(
            code="bot_runtime_config_invalid",
            message=f"Bot runtime `{field_name}` must be a mapping.",
            hint="Use YAML mapping syntax for runtime profile configuration.",
            details={"field": field_name},
            exit_code=2,
        )
    return dict(value)


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_float(value: Any, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _is_secret_field(lowered_key: str) -> bool:
    if lowered_key in {"endpoint_env", "endpoint_role"}:
        return False
    if lowered_key in {"max_tokens", "n_tokens", "token_budget"}:
        return False
    return any(marker in lowered_key for marker in SECRET_FIELD_MARKERS)


def endpoint_looks_operator_controlled(endpoint: str | None) -> bool:
    host = _endpoint_host(endpoint)
    if not host:
        return True
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host or host.endswith(".local") or host.endswith(".internal")
    return ip.is_private or ip.is_loopback or ip.is_link_local
