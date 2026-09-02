"""Local EmbeddingGemma provider for Repository Brain indexing."""

from __future__ import annotations

from collections.abc import Sequence
from importlib import import_module
from typing import Protocol, cast

import numpy as np

EMBEDDING_MODEL_ID = "ggml-org/embeddinggemma-300M-qat-q4_0-GGUF"
EMBEDDING_MODEL_FILE = "embeddinggemma-300M-qat-Q4_0.gguf"
EMBEDDING_DIMENSION = 512

_DOCUMENT_PROMPT = "title: none | text: "
_QUERY_PROMPT = "task: search result | query: "
_EMBEDDING_BATCH_SIZE = 16


class EmbeddingError(RuntimeError):
    """EmbeddingGemma could not load or satisfy its provider contract."""


class EmbeddingProvider(Protocol):
    """Small embedding boundary shared by index and query consumers."""

    @property
    def model_id(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def count_tokens(self, text: str) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


class _EmbeddingRuntime(Protocol):
    def tokenize(
        self,
        text: bytes,
        add_bos: bool = True,
        special: bool = False,
    ) -> list[int]: ...

    def embed(
        self,
        input: str | list[str],
        normalize: bool = False,
        truncate: bool = True,
    ) -> object: ...


class EmbeddingGemmaProvider:
    """In-process provider backed by the locked Q4 EmbeddingGemma GGUF."""

    def __init__(self, *, _runtime: _EmbeddingRuntime | None = None) -> None:
        self._runtime = _runtime or self._load_runtime()

    @property
    def model_id(self) -> str:
        return EMBEDDING_MODEL_ID

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIMENSION

    def count_tokens(self, text: str) -> int:
        try:
            return len(self._runtime.tokenize(text.encode("utf-8")))
        except Exception as error:
            raise EmbeddingError("EmbeddingGemma tokenization failed") from error

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        batches: list[np.ndarray] = []
        for start in range(0, len(texts), _EMBEDDING_BATCH_SIZE):
            prompted = [
                f"{_DOCUMENT_PROMPT}{text}"
                for text in texts[start : start + _EMBEDDING_BATCH_SIZE]
            ]
            batches.append(self._embed(prompted))
        return np.concatenate(batches, axis=0)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed(f"{_QUERY_PROMPT}{text}")[0]

    def _embed(self, texts: str | list[str]) -> np.ndarray:
        try:
            raw = self._runtime.embed(texts, normalize=False, truncate=True)
            vectors = np.asarray(raw, dtype=np.float32)
            if vectors.ndim == 1:
                vectors = vectors.reshape(1, -1)
            if vectors.ndim != 2 or vectors.shape[1] < self.dimension:
                raise ValueError(
                    "EmbeddingGemma returned an invalid embedding dimension"
                )
            vectors = np.ascontiguousarray(vectors[:, : self.dimension])
            if not np.isfinite(vectors).all():
                raise ValueError("EmbeddingGemma returned non-finite values")
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            if np.any(norms == 0):
                raise ValueError("EmbeddingGemma returned a zero vector")
            return np.ascontiguousarray(vectors / norms, dtype=np.float32)
        except EmbeddingError:
            raise
        except Exception as error:
            raise EmbeddingError("EmbeddingGemma encoding failed") from error

    @staticmethod
    def _load_runtime() -> _EmbeddingRuntime:
        try:
            llama = import_module("llama_cpp").Llama
            runtime = llama.from_pretrained(
                repo_id=EMBEDDING_MODEL_ID,
                filename=EMBEDDING_MODEL_FILE,
                embedding=True,
                n_ctx=2048,
                n_batch=2048,
                verbose=False,
            )
            return cast(_EmbeddingRuntime, runtime)
        except Exception as error:
            raise EmbeddingError("could not load local Q4 EmbeddingGemma") from error


__all__ = [
    "EMBEDDING_DIMENSION",
    "EMBEDDING_MODEL_ID",
    "EmbeddingError",
    "EmbeddingGemmaProvider",
    "EmbeddingProvider",
]
