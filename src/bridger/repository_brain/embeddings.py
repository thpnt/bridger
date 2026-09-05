"""Local EmbeddingGemma provider for Repository Brain indexing."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from importlib import import_module
from typing import Protocol, cast

import numpy as np

EMBEDDING_MODEL_ID = "google/embeddinggemma-300m"
EMBEDDING_DIMENSION = 512

_DENSE_FAILURES = (RuntimeError, TypeError, ValueError)
_LOGGER = logging.getLogger(__name__)


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


class _EmbeddingTokenizer(Protocol):
    def encode(
        self,
        text: str,
        *,
        add_special_tokens: bool = True,
    ) -> list[int]: ...


class _EmbeddingRuntime(Protocol):
    @property
    def tokenizer(self) -> _EmbeddingTokenizer: ...

    def encode_document(
        self,
        inputs: list[str],
        *,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
    ) -> object: ...

    def encode_query(
        self,
        inputs: str,
        *,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
    ) -> object: ...


class EmbeddingGemmaProvider:
    """Lazy in-process provider backed by canonical Sentence Transformers."""

    def __init__(self, *, _runtime: _EmbeddingRuntime | None = None) -> None:
        self._runtime = _runtime

    @property
    def model_id(self) -> str:
        return EMBEDDING_MODEL_ID

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIMENSION

    def count_tokens(self, text: str) -> int:
        try:
            return len(
                self._get_runtime().tokenizer.encode(
                    text,
                    add_special_tokens=True,
                )
            )
        except Exception as error:
            raise EmbeddingError("EmbeddingGemma tokenization failed") from error

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        try:
            inputs = list(texts)
            raw = self._get_runtime().encode_document(
                inputs,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            return self._validated_embeddings(raw, (len(inputs), self.dimension))
        except EmbeddingError:
            raise
        except Exception as error:
            raise EmbeddingError("EmbeddingGemma encoding failed") from error

    def embed_query(self, text: str) -> np.ndarray:
        try:
            raw = self._get_runtime().encode_query(
                text,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            return self._validated_embeddings(raw, (self.dimension,))
        except EmbeddingError:
            raise
        except Exception as error:
            raise EmbeddingError("EmbeddingGemma encoding failed") from error

    def _get_runtime(self) -> _EmbeddingRuntime:
        if self._runtime is None:
            self._runtime = self._load_runtime()
        return self._runtime

    @staticmethod
    def _validated_embeddings(raw: object, shape: tuple[int, ...]) -> np.ndarray:
        vectors = np.asarray(raw, dtype=np.float32)
        if vectors.shape != shape:
            raise EmbeddingError(
                f"EmbeddingGemma returned shape {vectors.shape}; expected {shape}"
            )
        if not np.isfinite(vectors).all():
            raise EmbeddingError("EmbeddingGemma returned non-finite values")
        norms = np.linalg.norm(vectors, axis=-1)
        if not np.allclose(norms, 1.0, rtol=1e-4, atol=1e-5):
            raise EmbeddingError("EmbeddingGemma returned unnormalized vectors")
        return np.ascontiguousarray(vectors, dtype=np.float32)

    @staticmethod
    def _load_runtime() -> _EmbeddingRuntime:
        try:
            _configure_model_output()
            sentence_transformer = import_module(
                "sentence_transformers"
            ).SentenceTransformer
            runtime = sentence_transformer(
                EMBEDDING_MODEL_ID,
                truncate_dim=EMBEDDING_DIMENSION,
            )
            return cast(_EmbeddingRuntime, runtime)
        except Exception as error:
            raise EmbeddingError("could not load EmbeddingGemma") from error


def _configure_model_output() -> None:
    """Keep routine model-library output out of Bridger's CLI presentation."""
    huggingface_utils = import_module("huggingface_hub.utils")
    huggingface_utils.disable_progress_bars()
    transformers_logging = import_module("transformers.utils.logging")
    transformers_logging.set_verbosity_error()
    logging.getLogger("sentence_transformers").setLevel(logging.ERROR)


class _UnavailableEmbeddingProvider:
    """Token-counting fallback used when dense embeddings are unavailable."""

    @property
    def model_id(self) -> str:
        return EMBEDDING_MODEL_ID

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIMENSION

    def count_tokens(self, text: str) -> int:
        return len(re.findall(r"\S+", text))

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        raise RuntimeError("dense embedding runtime is unavailable")

    def embed_query(self, text: str) -> np.ndarray:
        raise RuntimeError("dense embedding runtime is unavailable")


def resolve_embedding_provider(
    provider: EmbeddingProvider | None = None,
    *,
    require_runtime: bool = False,
) -> tuple[EmbeddingProvider, bool]:
    """Resolve the canonical provider or its lexical-only fallback."""
    if provider is None:
        provider = EmbeddingGemmaProvider()
    try:
        if provider.dimension != EMBEDDING_DIMENSION:
            raise ValueError("Brain embeddings must have 512 dimensions")
    except _DENSE_FAILURES:
        _LOGGER.warning(
            "embedding provider is incompatible; using BM25-only Brain indexing",
            exc_info=True,
        )
        return _UnavailableEmbeddingProvider(), False
    if require_runtime:
        try:
            provider.count_tokens("")
        except _DENSE_FAILURES:
            _LOGGER.warning(
                "EmbeddingGemma unavailable; using BM25-only Brain indexing",
                exc_info=True,
            )
            return _UnavailableEmbeddingProvider(), False
    return provider, True


__all__ = [
    "EMBEDDING_DIMENSION",
    "EMBEDDING_MODEL_ID",
    "EmbeddingError",
    "EmbeddingGemmaProvider",
    "EmbeddingProvider",
    "resolve_embedding_provider",
]
