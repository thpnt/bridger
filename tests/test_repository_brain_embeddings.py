"""Focused tests for the in-process EmbeddingGemma provider."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import bridger.repository_brain.embeddings as embeddings_module
from bridger.repository_brain.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_FILE,
    EMBEDDING_MODEL_ID,
    EmbeddingError,
    EmbeddingGemmaProvider,
)


class _FakeRuntime:
    def __init__(self, width: int = 768) -> None:
        self.width = width
        self.tokenized: list[bytes] = []
        self.embedded: list[tuple[str | list[str], bool, bool]] = []

    def tokenize(
        self,
        text: bytes,
        add_bos: bool = True,
        special: bool = False,
    ) -> list[int]:
        self.tokenized.append(text)
        return [0, *range(len(text.decode("utf-8").split()))]

    def embed(
        self,
        input: str | list[str],
        normalize: bool = False,
        truncate: bool = True,
    ) -> object:
        self.embedded.append((input, normalize, truncate))
        count = 1 if isinstance(input, str) else len(input)
        return np.tile(np.arange(1, self.width + 1), (count, 1))


def test_embeddinggemma_uses_model_tokenizer_and_distinct_prompts() -> None:
    runtime = _FakeRuntime()
    provider = EmbeddingGemmaProvider(_runtime=runtime)

    assert provider.model_id == EMBEDDING_MODEL_ID
    assert provider.dimension == EMBEDDING_DIMENSION
    assert provider.count_tokens("two tokens") == 3

    documents = provider.embed_documents(["first", "second"])
    query = provider.embed_query("question")

    assert runtime.tokenized == [b"two tokens"]
    assert runtime.embedded[0] == (
        ["title: none | text: first", "title: none | text: second"],
        False,
        True,
    )
    assert runtime.embedded[1] == (
        "task: search result | query: question",
        False,
        True,
    )
    assert documents.shape == (2, EMBEDDING_DIMENSION)
    assert query.shape == (EMBEDDING_DIMENSION,)
    assert np.allclose(np.linalg.norm(documents, axis=1), 1.0)
    assert np.isclose(np.linalg.norm(query), 1.0)


def test_embeddinggemma_enforces_dimension_contract() -> None:
    provider = EmbeddingGemmaProvider(_runtime=_FakeRuntime(width=32))

    with pytest.raises(EmbeddingError, match="encoding failed"):
        provider.embed_documents(["text"])


def test_embeddinggemma_loads_locked_gguf_through_upstream_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _FakeRuntime()
    calls: list[dict[str, object]] = []

    class FakeLlama:
        @classmethod
        def from_pretrained(cls, **kwargs: object) -> _FakeRuntime:
            calls.append(kwargs)
            return runtime

    monkeypatch.setattr(
        embeddings_module,
        "import_module",
        lambda _name: SimpleNamespace(Llama=FakeLlama),
    )

    provider = EmbeddingGemmaProvider()

    assert provider.count_tokens("cached model") == 3
    assert calls == [
        {
            "repo_id": EMBEDDING_MODEL_ID,
            "filename": EMBEDDING_MODEL_FILE,
            "embedding": True,
            "n_ctx": 2048,
            "n_batch": 2048,
            "verbose": False,
        }
    ]
