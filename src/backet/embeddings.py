from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

from backet.errors import AppError
from backet.local_runtime import DEFAULT_OLLAMA_EMBEDDING_MODEL, DEFAULT_OLLAMA_TIMEOUT_SECONDS, ollama_embed

DEFAULT_SENTENCE_MODEL = "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"
TOKEN_PATTERN = re.compile(r"[a-z0-9']+")


@dataclass(slots=True)
class EmbeddingResult:
    backend_name: str
    model_name: str
    vectors: list[list[float]]


class EmbeddingBackend:
    name: str
    model_name: str

    def encode_many(self, texts: list[str]) -> EmbeddingResult:
        raise NotImplementedError


class HashEmbeddingBackend(EmbeddingBackend):
    def __init__(self, dimensions: int = 64) -> None:
        self.name = "hash"
        self.model_name = f"hash-v1-{dimensions}"
        self.dimensions = dimensions

    def encode_many(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            backend_name=self.name,
            model_name=self.model_name,
            vectors=[self._encode_text(text) for text in texts],
        )

    def _encode_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for index in range(8):
                bucket = digest[index] % self.dimensions
                sign = 1.0 if digest[31 - index] % 2 == 0 else -1.0
                vector[bucket] += sign
        return normalize_vector(vector)


class SentenceTransformerEmbeddingBackend(EmbeddingBackend):
    def __init__(self, model_name: str = DEFAULT_SENTENCE_MODEL) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:  # pragma: no cover - covered via fallback logic
            raise AppError(
                code="embedding_backend_unavailable",
                message="Sentence Transformers is not installed for semantic vault retrieval.",
                hint="Install `sentence-transformers` or set BACKET_EMBEDDING_BACKEND=hash.",
                details={"requested_backend": "sentence-transformers", "model_name": model_name},
                exit_code=2,
            ) from exc

        self.name = "sentence-transformers"
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    def encode_many(self, texts: list[str]) -> EmbeddingResult:
        encoded = self._model.encode(texts, convert_to_numpy=False, normalize_embeddings=True)
        vectors: list[list[float]] = []
        for row in encoded:
            vectors.append([float(value) for value in row])
        return EmbeddingResult(
            backend_name=self.name,
            model_name=self.model_name,
            vectors=vectors,
        )


class OllamaEmbeddingBackend(EmbeddingBackend):
    def __init__(
        self,
        model_name: str = DEFAULT_OLLAMA_EMBEDDING_MODEL,
        *,
        endpoint: str | None = None,
        timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    ) -> None:
        self.name = "ollama"
        self.model_name = model_name
        self.endpoint = endpoint or os.environ.get("BACKET_OLLAMA_ENDPOINT")
        self.timeout_seconds = timeout_seconds

    def encode_many(self, texts: list[str]) -> EmbeddingResult:
        try:
            payload = ollama_embed(texts, model=self.model_name, endpoint=self.endpoint, timeout_seconds=self.timeout_seconds)
        except AppError:
            raise
        except Exception as exc:  # pragma: no cover - defensive guard around HTTP/runtime adapters.
            raise AppError(
                code="embedding_backend_unavailable",
                message="Ollama embedding backend is unavailable.",
                hint="Start Ollama, pull the configured embedding model, or set BACKET_EMBEDDING_BACKEND=hash.",
                details={"backend": self.name, "model_name": self.model_name, "error": str(exc)},
                exit_code=2,
            ) from exc
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise AppError(
                code="embedding_backend_invalid_response",
                message="Ollama returned an invalid embedding response.",
                hint="Check the Ollama version and embedding model.",
                details={"backend": self.name, "model_name": self.model_name},
                exit_code=2,
            )
        vectors: list[list[float]] = []
        for row in embeddings:
            if not isinstance(row, list):
                raise AppError(
                    code="embedding_backend_invalid_response",
                    message="Ollama returned a non-vector embedding row.",
                    hint="Use an embedding-capable Ollama model.",
                    details={"backend": self.name, "model_name": self.model_name},
                    exit_code=2,
                )
            vectors.append(normalize_vector([float(value) for value in row]))
        return EmbeddingResult(backend_name=self.name, model_name=str(payload.get("model") or self.model_name), vectors=vectors)


def resolve_embedding_backend() -> EmbeddingBackend:
    requested = os.environ.get("BACKET_EMBEDDING_BACKEND", "auto").strip().lower()
    return _resolve_backend(requested)


def resolve_embedding_backend_from_config(config: Mapping[str, object] | None) -> EmbeddingBackend:
    raw = dict(config or {})
    provider = str(raw.get("provider") or raw.get("backend") or "").strip().lower()
    if not provider or provider == "auto":
        return resolve_embedding_backend()
    if provider in {"hash", "hash-v1"}:
        dimensions = int(raw.get("dimensions") or 64)
        return HashEmbeddingBackend(dimensions=dimensions)
    if provider in {"ollama", "ollama-local", "ollama_local"}:
        endpoint_env = str(raw.get("endpoint_env") or raw.get("endpoint_role") or "").strip()
        endpoint = str(raw.get("endpoint") or os.environ.get(endpoint_env, "") or "").strip() or None
        timeout = float(raw.get("timeout_seconds") or raw.get("timeout") or DEFAULT_OLLAMA_TIMEOUT_SECONDS)
        return OllamaEmbeddingBackend(
            model_name=str(raw.get("model") or raw.get("model_id") or raw.get("name") or DEFAULT_OLLAMA_EMBEDDING_MODEL),
            endpoint=endpoint,
            timeout_seconds=timeout,
        )
    if provider in {"sentence-transformers", "sentence_transformers"}:
        return SentenceTransformerEmbeddingBackend(model_name=str(raw.get("model") or raw.get("model_id") or DEFAULT_SENTENCE_MODEL))
    raise AppError(
        code="embedding_backend_unknown",
        message=f"Unknown embedding backend: {provider}",
        hint="Use provider/backend hash, ollama, sentence-transformers, or auto.",
        details={"requested_backend": provider},
        exit_code=2,
    )


@lru_cache(maxsize=4)
def _resolve_backend(requested: str) -> EmbeddingBackend:
    if requested == "hash":
        return HashEmbeddingBackend()
    if requested in {"ollama", "ollama-local", "ollama_local"}:
        return OllamaEmbeddingBackend(
            model_name=os.environ.get("BACKET_EMBEDDING_MODEL", DEFAULT_OLLAMA_EMBEDDING_MODEL),
            endpoint=os.environ.get("BACKET_OLLAMA_ENDPOINT"),
            timeout_seconds=float(os.environ.get("BACKET_EMBEDDING_TIMEOUT", DEFAULT_OLLAMA_TIMEOUT_SECONDS)),
        )
    if requested in {"auto", "", "sentence-transformers", "sentence_transformers"}:
        try:
            return SentenceTransformerEmbeddingBackend()
        except AppError:
            if requested == "auto":
                return HashEmbeddingBackend()
            raise
    raise AppError(
        code="embedding_backend_unknown",
        message=f"Unknown embedding backend: {requested}",
        hint="Use BACKET_EMBEDDING_BACKEND=auto, ollama, sentence-transformers, or hash.",
        details={"requested_backend": requested},
        exit_code=2,
    )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=False))


def normalize_vector(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]
