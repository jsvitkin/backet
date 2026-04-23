from __future__ import annotations

import pytest

from backet.embeddings import HashEmbeddingBackend, cosine_similarity, resolve_embedding_backend
from backet.errors import AppError


def test_hash_embedding_backend_normalizes_vectors() -> None:
    backend = HashEmbeddingBackend(dimensions=16)
    result = backend.encode_many(["blood doll addiction", "court etiquette"])

    assert result.backend_name == "hash"
    assert len(result.vectors) == 2
    assert len(result.vectors[0]) == 16
    assert round(sum(value * value for value in result.vectors[0]), 6) == 1.0
    assert cosine_similarity(result.vectors[0], result.vectors[0]) == pytest.approx(1.0)


def test_resolve_embedding_backend_auto_falls_back_to_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKET_EMBEDDING_BACKEND", "auto")

    backend = resolve_embedding_backend()

    assert backend.name == "hash"


def test_resolve_embedding_backend_rejects_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKET_EMBEDDING_BACKEND", "mystery")

    with pytest.raises(AppError, match="Unknown embedding backend"):
        resolve_embedding_backend()
