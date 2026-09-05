"""Focused deterministic chunking and SQLite Brain index tests."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import numpy as np
import pytest

import bridger.repository_brain.index as index_module
from bridger.contracts.repository_brain import RepositoryBrainManifest
from bridger.repository_brain.embeddings import EMBEDDING_MODEL_ID
from bridger.repository_brain.index import (
    BRAIN_CHUNK_OVERLAP_TOKENS,
    BRAIN_CHUNK_TARGET_TOKENS,
    BrainIndexError,
    _chunk_document,
    build_brain_index,
    ensure_brain_index,
    require_brain_index,
)
from bridger.repository_brain.loader import BrainDocument, LoadedRepositoryBrain


class _FakeEmbeddingProvider:
    model_id = "fake-embeddinggemma-q4"
    dimension = 512

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.embed_calls = 0

    def count_tokens(self, text: str) -> int:
        return len(re.findall(r"\S+", text))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        self.embed_calls += 1
        if self.fail:
            raise RuntimeError("dense runtime unavailable")
        vectors = np.ones((len(texts), self.dimension), dtype=np.float32)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    def embed_query(self, text: str) -> np.ndarray:
        vector = np.ones(self.dimension, dtype=np.float32)
        return vector / np.linalg.norm(vector)


def test_markdown_chunking_is_deterministic_and_preserves_provenance() -> None:
    provider = _FakeEmbeddingProvider()
    long_lines = [
        " ".join(f"word_{line}_{token}" for token in range(10)) for line in range(70)
    ]
    content = "# Root\n" + "\n".join(long_lines) + "\n## Next\nnext body"
    document = _document("doc-1", "architecture/runtime.md", content)

    first = _chunk_document(document, provider)
    second = _chunk_document(document, provider)

    assert first == second
    assert [chunk.chunk_id for chunk in first] == [
        f"doc-1:{ordinal}" for ordinal in range(len(first))
    ]
    assert all(chunk.text.strip() for chunk in first)
    assert all(chunk.start_line <= chunk.end_line for chunk in first)
    assert first[0].heading_path == "Root"
    next_chunk = next(chunk for chunk in first if chunk.heading_path == "Root > Next")
    assert next_chunk.text.startswith("## Next")
    overlap = set(first[0].text.split()) & set(first[1].text.split())
    assert 50 <= len(overlap) <= BRAIN_CHUNK_OVERLAP_TOKENS
    assert provider.count_tokens(first[0].text) <= BRAIN_CHUNK_TARGET_TOKENS
    assert first[1].start_line <= first[0].end_line


def test_chunking_prefers_paragraphs_and_keeps_oversized_lines_atomic() -> None:
    provider = _FakeEmbeddingProvider()
    paragraph_one = " ".join(f"first_{index}" for index in range(400))
    paragraph_two = " ".join(f"second_{index}" for index in range(200))
    paragraph_document = _document(
        "paragraphs",
        "design/paragraphs.md",
        f"# Paragraphs\n\n{paragraph_one}\n\n{paragraph_two}",
    )

    chunks = _chunk_document(paragraph_document, provider)

    assert len(chunks) == 2
    assert "first_399" in chunks[0].text
    assert "second_0" not in chunks[0].text
    assert chunks[1].text.startswith("second_0")

    oversized = " ".join(f"large_{index}" for index in range(600))
    oversized_chunks = _chunk_document(
        _document("oversized", "testing/large.md", oversized),
        provider,
    )
    assert len(oversized_chunks) == 1
    assert provider.count_tokens(oversized_chunks[0].text) == 600
    assert oversized_chunks[0].start_line == oversized_chunks[0].end_line == 1


def test_sqlite_index_contains_documents_chunks_fts_links_and_vectors(
    tmp_path: Path,
) -> None:
    brain = _brain()
    provider = _FakeEmbeddingProvider()

    index_path = build_brain_index(brain, tmp_path / ".bridger" / "cache", provider)

    assert index_path == (
        tmp_path
        / ".bridger"
        / "cache"
        / "brain"
        / brain.publication_id
        / "brain.sqlite3"
    )
    with sqlite3.connect(index_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        assert {"metadata", "documents", "chunks", "links", "chunks_fts"} <= tables
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone() == (2,)
        assert connection.execute(
            "SELECT title FROM documents WHERE document_id = 'architecture-doc'"
        ).fetchone() == ("Runtime",)
        chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert connection.execute("SELECT COUNT(*) FROM chunks_fts").fetchone() == (
            chunk_count,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM chunks WHERE length(embedding) = 2048"
        ).fetchone() == (chunk_count,)
        assert connection.execute("SELECT COUNT(*) FROM links").fetchone() == (1,)
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        assert metadata["publication_id"] == brain.publication_id
        assert metadata["embedding_model_id"] == provider.model_id
        assert metadata["embedding_dimension"] == "512"


def test_embedding_failure_keeps_valid_searchable_lexical_index(
    tmp_path: Path,
) -> None:
    provider = _FakeEmbeddingProvider(fail=True)
    index_path = build_brain_index(_brain(), tmp_path, provider)

    with sqlite3.connect(index_path) as connection:
        chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert connection.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedding IS NULL"
        ).fetchone() == (chunk_count,)
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH 'authority'"
            ).fetchone()[0]
            >= 1
        )
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        assert "embedding_model_id" not in metadata
        assert "embedding_dimension" not in metadata


def test_ensure_reuses_valid_cache_and_rebuilds_stale_metadata(
    tmp_path: Path,
) -> None:
    brain = _brain()
    provider = _FakeEmbeddingProvider()
    cache_root = tmp_path / "cache"
    first = ensure_brain_index(brain, cache_root, provider)

    assert ensure_brain_index(brain, cache_root, provider) == first
    assert provider.embed_calls == 1

    with sqlite3.connect(first) as connection:
        connection.execute(
            "UPDATE metadata SET value = '999' WHERE key = 'chunk_target_tokens'"
        )
    assert ensure_brain_index(brain, cache_root, provider) == first
    assert provider.embed_calls == 2
    assert first.is_file()
    with sqlite3.connect(first) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key = 'chunk_target_tokens'"
        ).fetchone() == (str(BRAIN_CHUNK_TARGET_TOKENS),)


def test_ensure_rebuilds_index_with_old_gguf_model_identity(tmp_path: Path) -> None:
    brain = _brain()
    provider = _FakeEmbeddingProvider()
    provider.model_id = EMBEDDING_MODEL_ID
    index_path = ensure_brain_index(brain, tmp_path, provider)
    with sqlite3.connect(index_path) as connection:
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'embedding_model_id'",
            ("ggml-org/embeddinggemma-300M-qat-q4_0-GGUF",),
        )

    assert ensure_brain_index(brain, tmp_path, provider) == index_path
    assert provider.embed_calls == 2
    with sqlite3.connect(index_path) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    assert metadata["embedding_model_id"] == EMBEDDING_MODEL_ID


def test_ensure_reuses_canonical_index_without_resolving_embedding_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brain = _brain()
    provider = _FakeEmbeddingProvider()
    provider.model_id = EMBEDDING_MODEL_ID
    index_path = build_brain_index(brain, tmp_path, provider)
    monkeypatch.setattr(
        index_module,
        "resolve_embedding_provider",
        lambda: pytest.fail("compatible metadata must avoid provider resolution"),
    )

    assert ensure_brain_index(brain, tmp_path) == index_path


def test_require_returns_compatible_index_without_building(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brain = _brain()
    provider = _FakeEmbeddingProvider()
    index_path = build_brain_index(brain, tmp_path, provider)
    monkeypatch.setattr(
        index_module,
        "build_brain_index",
        lambda *_args: pytest.fail("require must not build an index"),
    )

    assert require_brain_index(brain, tmp_path, provider) == index_path


def test_require_rejects_missing_index_without_creating_it(tmp_path: Path) -> None:
    brain = _brain()
    expected = tmp_path / "brain" / brain.publication_id / "brain.sqlite3"

    with pytest.raises(BrainIndexError, match="compatible.*unavailable"):
        require_brain_index(brain, tmp_path, _FakeEmbeddingProvider())

    assert not expected.exists()


def test_require_rejects_incompatible_index_without_rebuilding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brain = _brain()
    provider = _FakeEmbeddingProvider()
    index_path = build_brain_index(brain, tmp_path, provider)
    with sqlite3.connect(index_path) as connection:
        connection.execute(
            "UPDATE metadata SET value = '999' WHERE key = 'chunk_target_tokens'"
        )
    stale = index_path.read_bytes()
    monkeypatch.setattr(
        index_module,
        "build_brain_index",
        lambda *_args: pytest.fail("require must not rebuild an index"),
    )

    with pytest.raises(BrainIndexError, match="compatible.*unavailable"):
        require_brain_index(brain, tmp_path, provider)

    assert index_path.read_bytes() == stale


def test_failed_atomic_rebuild_does_not_replace_valid_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brain = _brain()
    provider = _FakeEmbeddingProvider()
    index_path = build_brain_index(brain, tmp_path, provider)
    original = index_path.read_bytes()

    def fail_population(*_args: object) -> None:
        raise RuntimeError("interrupted")

    monkeypatch.setattr(index_module, "_populate_index", fail_population)
    with pytest.raises(BrainIndexError, match="could not build"):
        build_brain_index(brain, tmp_path, provider)

    assert index_path.read_bytes() == original
    assert not list(index_path.parent.glob("brain.sqlite3.tmp-*"))


def _brain() -> LoadedRepositoryBrain:
    documents = (
        _document(
            "architecture-doc",
            "architecture/runtime.md",
            "# Runtime\n\nSee [state](../data/state.md#authority).\n",
            owner="architecture",
        ),
        _document(
            "state-doc",
            "data/state.md",
            "# State\n\nThe database is the state authority.\n",
            owner="data",
        ),
    )
    manifest = RepositoryBrainManifest(
        repository_id="repository-1",
        repository_revision="revision-1",
        graph_snapshot_id="snapshot-1",
        graph_snapshot_root="/graph/snapshot-1",
        enrichment_overlay_id="overlay-1",
        fleet_run_id="fleet-1",
        memory_runtime_root="/runtime",
        memory_output_root="/memory",
        accepted_memory_fleet_result_id="accepted-fleet-1",
        memory_target_catalog_id="catalog-1",
        memory_target_catalog_version="1",
        accepted_target_result_refs=["accepted-architecture", "accepted-data"],
    )
    return LoadedRepositoryBrain(
        publication_id="publication-1",
        manifest=manifest,
        documents=documents,
    )


def _document(
    document_id: str,
    relative_path: str,
    content: str,
    *,
    owner: str = "owner",
) -> BrainDocument:
    return BrainDocument(
        document_id=document_id,
        semantic_owner=owner,
        relative_path=relative_path,
        artifact_revision=1,
        digest=f"digest-{document_id}",
        content=content,
    )
