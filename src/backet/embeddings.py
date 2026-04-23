from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache

from backet.errors import AppError

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


def resolve_embedding_backend() -> EmbeddingBackend:
    requested = os.environ.get("BACKET_EMBEDDING_BACKEND", "auto").strip().lower()
    return _resolve_backend(requested)


@lru_cache(maxsize=4)
def _resolve_backend(requested: str) -> EmbeddingBackend:
    if requested == "hash":
        return HashEmbeddingBackend()
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
        hint="Use BACKET_EMBEDDING_BACKEND=auto, sentence-transformers, or hash.",
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
