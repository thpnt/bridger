"""Focused tests for the in-process EmbeddingGemma provider."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import bridger.repository_brain.embeddings as embeddings_module
from bridger.repository_brain.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_ID,
    EmbeddingError,
    EmbeddingGemmaProvider,
    resolve_embedding_provider,
)


class _FakeTokenizer:
    def __init__(self, tokens: list[int] | None = None) -> None:
        self.tokens = tokens or [1, 2, 3]
        self.calls: list[tuple[str, bool]] = []

    def encode(self, text: str, *, add_special_tokens: bool = True) -> list[int]:
        self.calls.append((text, add_special_tokens))
        return self.tokens


class _FakeRuntime:
    def __init__(self) -> None:
        self.tokenizer = _FakeTokenizer()
        self.document_calls: list[tuple[list[str], bool, bool]] = []
        self.query_calls: list[tuple[str, bool, bool]] = []
        self.document_output: object | None = None
        self.query_output: object | None = None
        self.document_error: Exception | None = None
        self.query_error: Exception | None = None

    def encode_document(
        self,
        inputs: list[str],
        *,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
    ) -> object:
        self.document_calls.append((inputs, normalize_embeddings, convert_to_numpy))
        if self.document_error is not None:
            raise self.document_error
        if self.document_output is not None:
            return self.document_output
        return _unit_vectors(len(inputs))

    def encode_query(
        self,
        inputs: str,
        *,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
    ) -> object:
        self.query_calls.append((inputs, normalize_embeddings, convert_to_numpy))
        if self.query_error is not None:
            raise self.query_error
        if self.query_output is not None:
            return self.query_output
        return _unit_vectors(1)[0]


def _unit_vectors(count: int) -> np.ndarray:
    vectors = np.zeros((count, EMBEDDING_DIMENSION), dtype=np.float64)
    vectors[:, 0] = 1.0
    return vectors


def test_embeddinggemma_uses_native_retrieval_methods_and_model_tokenizer() -> None:
    runtime = _FakeRuntime()
    runtime.tokenizer = _FakeTokenizer([10, 20, 30, 40])
    provider = EmbeddingGemmaProvider(_runtime=runtime)

    assert provider.model_id == "google/embeddinggemma-300m" == EMBEDDING_MODEL_ID
    assert provider.dimension == 512 == EMBEDDING_DIMENSION
    assert provider.count_tokens("two words") == 4

    documents = provider.embed_documents(["first", "second"])
    query = provider.embed_query("question")

    assert runtime.tokenizer.calls == [("two words", True)]
    assert runtime.document_calls == [(["first", "second"], True, True)]
    assert runtime.query_calls == [("question", True, True)]
    assert documents.shape == (2, EMBEDDING_DIMENSION)
    assert query.shape == (EMBEDDING_DIMENSION,)
    assert documents.dtype == query.dtype == np.float32
    assert np.allclose(np.linalg.norm(documents, axis=1), 1.0)
    assert np.isclose(np.linalg.norm(query), 1.0)


def test_embeddinggemma_runtime_construction_is_lazy_and_device_agnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _FakeRuntime()
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def sentence_transformer(*args: object, **kwargs: object) -> _FakeRuntime:
        calls.append((args, kwargs))
        return runtime

    monkeypatch.setattr(
        embeddings_module,
        "import_module",
        lambda name: (
            SimpleNamespace(disable_progress_bars=lambda: None)
            if name == "huggingface_hub.utils"
            else SimpleNamespace(set_verbosity_error=lambda: None)
            if name == "transformers.utils.logging"
            else SimpleNamespace(SentenceTransformer=sentence_transformer)
        ),
    )

    provider = EmbeddingGemmaProvider()

    assert provider.model_id == EMBEDDING_MODEL_ID
    assert provider.dimension == EMBEDDING_DIMENSION
    assert calls == []

    assert provider.count_tokens("cached model") == 3
    assert calls == [((EMBEDDING_MODEL_ID,), {"truncate_dim": EMBEDDING_DIMENSION})]
    assert "device" not in calls[0][1]
    assert provider.count_tokens("same runtime") == 3
    assert len(calls) == 1


def test_model_output_configuration_disables_only_routine_library_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def import_fake(name: str) -> SimpleNamespace:
        if name == "huggingface_hub.utils":
            return SimpleNamespace(disable_progress_bars=lambda: calls.append("hub"))
        if name == "transformers.utils.logging":
            return SimpleNamespace(
                set_verbosity_error=lambda: calls.append("transformers")
            )
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(embeddings_module, "import_module", import_fake)
    logger = embeddings_module.logging.getLogger("sentence_transformers")
    monkeypatch.setattr(logger, "setLevel", lambda level: calls.append(str(level)))

    embeddings_module._configure_model_output()

    assert calls == ["hub", "transformers", str(embeddings_module.logging.ERROR)]


def test_empty_document_sequence_does_not_load_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        embeddings_module,
        "import_module",
        lambda _name: pytest.fail("empty input must not load the runtime"),
    )

    result = EmbeddingGemmaProvider().embed_documents([])

    assert result.shape == (0, EMBEDDING_DIMENSION)
    assert result.dtype == np.float32


@pytest.mark.parametrize(
    "output",
    [
        np.zeros(EMBEDDING_DIMENSION),
        np.zeros((1, EMBEDDING_DIMENSION)),
        np.zeros((2, 32)),
        np.full((2, EMBEDDING_DIMENSION), np.nan),
        np.full((2, EMBEDDING_DIMENSION), np.inf),
        np.zeros((2, EMBEDDING_DIMENSION)),
        "malformed",
    ],
)
def test_embeddinggemma_rejects_invalid_document_output(output: object) -> None:
    runtime = _FakeRuntime()
    runtime.document_output = output
    provider = EmbeddingGemmaProvider(_runtime=runtime)

    with pytest.raises(EmbeddingError):
        provider.embed_documents(["first", "second"])


@pytest.mark.parametrize(
    "output",
    [
        np.zeros((1, EMBEDDING_DIMENSION)),
        np.zeros(32),
        np.full(EMBEDDING_DIMENSION, np.nan),
        np.zeros(EMBEDDING_DIMENSION),
        {"malformed": True},
    ],
)
def test_embeddinggemma_rejects_invalid_query_output(output: object) -> None:
    runtime = _FakeRuntime()
    runtime.query_output = output
    provider = EmbeddingGemmaProvider(_runtime=runtime)

    with pytest.raises(EmbeddingError):
        provider.embed_query("question")


@pytest.mark.parametrize("method", ["documents", "query"])
def test_embeddinggemma_translates_runtime_exceptions(method: str) -> None:
    runtime = _FakeRuntime()
    provider = EmbeddingGemmaProvider(_runtime=runtime)
    with pytest.raises(EmbeddingError, match="encoding failed"):
        if method == "documents":
            runtime.document_error = OSError("inference failed")
            provider.embed_documents(["text"])
        else:
            runtime.query_error = OSError("inference failed")
            provider.embed_query("text")


def test_embeddinggemma_translates_tokenizer_and_import_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _FakeRuntime()

    def fail_tokenization(
        _text: str,
        *,
        add_special_tokens: bool = True,
    ) -> list[int]:
        raise OSError("tokenizer failed")

    runtime.tokenizer.encode = fail_tokenization
    with pytest.raises(EmbeddingError, match="tokenization failed"):
        EmbeddingGemmaProvider(_runtime=runtime).count_tokens("not heuristic")

    monkeypatch.setattr(
        embeddings_module,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ImportError("missing runtime")),
    )
    provider = EmbeddingGemmaProvider()
    with pytest.raises(EmbeddingError, match="tokenization failed"):
        provider.count_tokens("load lazily")


def test_runtime_requirement_uses_existing_lexical_fallback() -> None:
    runtime = _FakeRuntime()

    def fail_tokenization(
        _text: str,
        *,
        add_special_tokens: bool = True,
    ) -> list[int]:
        raise OSError("tokenizer failed")

    runtime.tokenizer.encode = fail_tokenization

    provider, available = resolve_embedding_provider(
        EmbeddingGemmaProvider(_runtime=runtime),
        require_runtime=True,
    )

    assert not available
    assert provider.count_tokens("lexical fallback") == 2
