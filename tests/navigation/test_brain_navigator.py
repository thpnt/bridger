"""Focused BrainNavigator V0 retrieval and progressive-read behavior."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import numpy as np
import pytest

import bridger.navigation.brain as brain_module
from bridger.contracts.consumption import (
    Authority,
    BridgerRef,
    BridgerRefKind,
    IntelligenceQueryRequest,
    IntelligenceReadRequest,
    Lens,
    ReadExpansion,
    ResultOperation,
    ScopeKind,
    ScopeRef,
    Substrate,
)
from bridger.contracts.repository_brain import RepositoryBrainManifest
from bridger.navigation import BrainNavigator
from bridger.repository_brain.loader import BrainDocument, LoadedRepositoryBrain


class _FakeEmbeddingProvider:
    model_id = "fake-embeddinggemma-q4"
    dimension = 512

    def __init__(
        self,
        *,
        fail_documents: bool = False,
        fail_queries: bool = False,
    ) -> None:
        self.fail_documents = fail_documents
        self.fail_queries = fail_queries
        self.query_calls: list[str] = []

    def count_tokens(self, text: str) -> int:
        return len(re.findall(r"\S+", text))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if self.fail_documents:
            raise RuntimeError("dense document runtime unavailable")
        return np.stack([self._vector(text) for text in texts])

    def embed_query(self, text: str) -> np.ndarray:
        self.query_calls.append(text)
        if self.fail_queries:
            raise RuntimeError("dense query runtime unavailable")
        vector = np.zeros(self.dimension, dtype=np.float32)
        vector[0] = 1
        return vector

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimension, dtype=np.float32)
        if "completion obligations" in text or "accepted_target_result" in text:
            vector[0] = 1
        else:
            vector[1] = 1
        return vector


@pytest.fixture
def loaded_brain(tmp_path: Path) -> LoadedRepositoryBrain:
    documents = (
        _document(
            "repository-doc",
            "repository/orientation.md",
            "# Repository Orientation\n\n"
            "BrainNavigator provides broad repository orientation.\n",
            owner="repository",
        ),
        _document(
            "acceptance-doc",
            "business/acceptance.md",
            "# TargetPhase Retry\n\n"
            "accepted_target_result retry idempotency rules and completion "
            "obligations govern finalization.\n",
            owner="business-logic",
        ),
        _document(
            "finalization-doc",
            "architecture/finalization.md",
            "# Finalization\n\n"
            "Uninvestigated completion obligations block finalization readiness.\n",
            owner="architecture",
        ),
        _document(
            "retry-doc",
            "testing/retry.md",
            "# Retry Policy\n\n"
            "RetryScheduler handles retry-policy validation and idempotency.\n",
            owner="testing",
        ),
        _document(
            "path-doc",
            "interfaces/navigation.md",
            "# Navigation Module\n\n"
            "The canonical path is src/bridger/navigation/brain.py.\n",
            owner="interfaces-and-integrations",
        ),
        _document(
            "title-doc",
            "architecture/target-phase.md",
            "# TargetPhase\n\nLifecycle details live here.\n",
            owner="architecture",
        ),
        _document(
            "body-doc",
            "conventions/workflow.md",
            "# Workflow Notes\n\n"
            "TargetPhase is mentioned only in ordinary body text.\n",
            owner="conventions",
        ),
        _document(
            "collapse-doc",
            "testing/collapse.md",
            "# Collapse Fixture\n"
            "## First specialtoken\n"
            "First canonical passage.\n"
            "## Second specialtoken\n"
            "Second canonical passage.\n"
            "## Gap\n"
            "Unrelated material separates local areas.\n"
            "## Distant specialtoken\n"
            "Distant canonical passage.\n",
            owner="testing",
        ),
    )
    memory_root = tmp_path / ".bridger" / "memory"
    return LoadedRepositoryBrain(
        publication_id="publication-1",
        manifest=RepositoryBrainManifest(
            repository_id="repository-1",
            repository_revision="revision-1",
            graph_snapshot_id="snapshot-1",
            graph_snapshot_root=str(tmp_path / "graph"),
            enrichment_overlay_id="overlay-1",
            fleet_run_id="fleet-1",
            memory_runtime_root=str(tmp_path / "runtime"),
            memory_output_root=str(memory_root),
            accepted_memory_fleet_result_id="accepted-fleet-1",
            memory_target_catalog_id="catalog-1",
            memory_target_catalog_version="1",
            accepted_target_result_refs=["accepted-target-1"],
        ),
        documents=documents,
    )


def _navigator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loaded_brain: LoadedRepositoryBrain,
    provider: _FakeEmbeddingProvider,
) -> BrainNavigator:
    monkeypatch.setattr(
        brain_module,
        "_load_repository_brain",
        lambda _publication_path: loaded_brain,
    )
    navigator = BrainNavigator(
        tmp_path / "repository-brain.json",
        embedding_provider=provider,
    )
    expected_index = (
        tmp_path
        / ".bridger"
        / "cache"
        / "brain"
        / loaded_brain.publication_id
        / "brain.sqlite3"
    )
    assert expected_index.is_file()
    return navigator


def test_close_closes_the_owned_sqlite_connection_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loaded_brain: LoadedRepositoryBrain,
) -> None:
    navigator = _navigator(
        tmp_path,
        monkeypatch,
        loaded_brain,
        _FakeEmbeddingProvider(),
    )
    connection = navigator._connection

    navigator.close()
    navigator.close()

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_context_manager_preserves_search_and_read_and_closes_on_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loaded_brain: LoadedRepositoryBrain,
) -> None:
    navigator = _navigator(
        tmp_path,
        monkeypatch,
        loaded_brain,
        _FakeEmbeddingProvider(),
    )
    connection = navigator._connection
    ref = BridgerRef(
        kind=BridgerRefKind.BRAIN_DOCUMENT,
        target_ref={"document_id": "repository-doc"},
        repository_revision="revision-1",
    )

    with navigator as entered:
        assert entered is navigator
        assert navigator.search(
            IntelligenceQueryRequest(lens=Lens.UNDERSTAND, query="TargetPhase")
        ).items
        assert navigator.read(IntelligenceReadRequest(ref=ref)).items

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_context_manager_propagates_exception_and_still_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loaded_brain: LoadedRepositoryBrain,
) -> None:
    navigator = _navigator(
        tmp_path,
        monkeypatch,
        loaded_brain,
        _FakeEmbeddingProvider(),
    )
    connection = navigator._connection

    with pytest.raises(RuntimeError, match="boom"):
        with navigator:
            raise RuntimeError("boom")

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_bm25_fallback_is_safe_weighted_bounded_and_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loaded_brain: LoadedRepositoryBrain,
) -> None:
    provider = _FakeEmbeddingProvider(fail_queries=True)
    navigator = _navigator(tmp_path, monkeypatch, loaded_brain, provider)
    request = IntelligenceQueryRequest(
        lens=Lens.UNDERSTAND,
        query="TargetPhase",
        limit=20,
    )

    first = navigator.search(request)
    second = navigator.search(request)

    titles = [item.title for item in first.items]
    assert titles.index("TargetPhase") < titles.index("Workflow Notes")
    assert first == second
    assert provider.query_calls == ["TargetPhase"]
    assert first.operation is ResultOperation.QUERY
    assert len(first.items) <= 20

    unsafe_inputs = (
        "src/bridger/navigation/brain.py",
        "RetryScheduler",
        "foo::bar",
        "A->B",
        '"quoted text"',
        "foo:bar",
        "retry-policy",
        "TargetPhase OR specialtoken",
    )
    for text in unsafe_inputs:
        result = navigator.search(
            IntelligenceQueryRequest(lens=Lens.UNDERSTAND, query=text)
        )
        repeated = navigator.search(
            IntelligenceQueryRequest(lens=Lens.UNDERSTAND, query=text)
        )
        assert result == repeated
    assert provider.query_calls == ["TargetPhase"]


def test_lexical_index_without_vectors_never_attempts_dense_retrieval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loaded_brain: LoadedRepositoryBrain,
) -> None:
    provider = _FakeEmbeddingProvider(fail_documents=True)
    navigator = _navigator(tmp_path, monkeypatch, loaded_brain, provider)

    result = navigator.search(
        IntelligenceQueryRequest(lens=Lens.UNDERSTAND, query="RetryScheduler")
    )

    assert result.items[0].title == "Retry Policy"
    assert provider.query_calls == []


def test_hybrid_search_retrieves_lexical_and_semantic_passages_with_stable_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loaded_brain: LoadedRepositoryBrain,
) -> None:
    provider = _FakeEmbeddingProvider()
    navigator = _navigator(tmp_path, monkeypatch, loaded_brain, provider)

    hybrid = navigator.search(
        IntelligenceQueryRequest(lens=Lens.GUARDRAILS, query="retry", limit=20)
    )
    semantic = navigator.search(
        IntelligenceQueryRequest(
            lens=Lens.UNDERSTAND,
            query="prevent worker finishing too early",
        )
    )

    hybrid_titles = [item.title for item in hybrid.items]
    assert hybrid_titles[0] == "TargetPhase Retry"
    assert "Retry Policy" in hybrid_titles
    assert "Finalization" in hybrid_titles
    assert semantic.items[0].title == "Finalization"
    assert provider.query_calls == ["retry", "prevent worker finishing too early"]
    for item in hybrid.items:
        assert item.ref.repository_revision == "revision-1"
        assert item.provenance.repository_revision == "revision-1"
        assert item.provenance.substrate is Substrate.BRAIN
        assert item.provenance.authority is Authority.DERIVED
        assert item.kind is BridgerRefKind.BRAIN_CONTEXT
        assert item.matched_claim_refs == []
        assert item.evidence_refs == []
        assert item.related_refs == []


def test_scope_only_requests_use_deterministic_brain_signals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loaded_brain: LoadedRepositoryBrain,
) -> None:
    provider = _FakeEmbeddingProvider()
    navigator = _navigator(tmp_path, monkeypatch, loaded_brain, provider)

    understand = navigator.search(
        IntelligenceQueryRequest(
            lens=Lens.UNDERSTAND,
            scope=ScopeRef(kind=ScopeKind.REPOSITORY),
        )
    )
    guardrails = navigator.search(
        IntelligenceQueryRequest(
            lens=Lens.GUARDRAILS,
            scope=ScopeRef(kind=ScopeKind.REPOSITORY),
        )
    )
    path = navigator.search(
        IntelligenceQueryRequest(
            lens=Lens.UNDERSTAND,
            scope=ScopeRef(
                kind=ScopeKind.PATH,
                value="src/bridger/navigation/brain.py",
            ),
        )
    )
    symbol = navigator.search(
        IntelligenceQueryRequest(
            lens=Lens.GUARDRAILS,
            scope=ScopeRef(kind=ScopeKind.SYMBOL, value="RetryScheduler"),
        )
    )
    graph = navigator.search(
        IntelligenceQueryRequest(
            lens=Lens.UNDERSTAND,
            scope=ScopeRef(
                kind=ScopeKind.GRAPH_ENTITY,
                value={"node_id": "accepted_target_result"},
            ),
        )
    )

    assert understand.items[0].title == "Repository Orientation"
    assert guardrails.items[0].semantic_owner == "business-logic"
    assert path.items[0].title == "Navigation Module"
    assert symbol.items[0].title == "Retry Policy"
    assert graph.items[0].title == "TargetPhase Retry"
    assert provider.query_calls == [
        "src/bridger/navigation/brain.py",
        "RetryScheduler",
        '{"node_id":"accepted_target_result"}',
    ]

    context_ref = BridgerRef(
        kind=BridgerRefKind.BRAIN_CONTEXT,
        target_ref={
            "document_id": "acceptance-doc",
            "start_line": 1,
            "end_line": 3,
        },
        repository_revision="revision-1",
    )
    calls_before = list(provider.query_calls)
    direct = navigator.search(
        IntelligenceQueryRequest(
            lens=Lens.UNDERSTAND,
            scope=ScopeRef(kind=ScopeKind.BRAIN_REF, value=context_ref),
        )
    )

    assert direct.items[0].ref == context_ref
    assert direct.items[0].content == loaded_brain.documents[1].content
    assert provider.query_calls == calls_before


def test_nearby_hits_collapse_without_merging_distant_areas_and_report_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loaded_brain: LoadedRepositoryBrain,
) -> None:
    navigator = _navigator(
        tmp_path,
        monkeypatch,
        loaded_brain,
        _FakeEmbeddingProvider(fail_queries=True),
    )

    result = navigator.search(
        IntelligenceQueryRequest(
            lens=Lens.UNDERSTAND,
            query="specialtoken",
            limit=1,
        )
    )
    all_results = navigator.search(
        IntelligenceQueryRequest(
            lens=Lens.UNDERSTAND,
            query="specialtoken",
            limit=20,
        )
    )

    assert len(all_results.items) == 2
    first_target = all_results.items[0].ref.target_ref
    second_target = all_results.items[1].ref.target_ref
    assert isinstance(first_target, dict)
    assert isinstance(second_target, dict)
    assert first_target["document_id"] == second_target["document_id"] == "collapse-doc"
    assert first_target["end_line"] < second_target["start_line"]
    assert all_results.items[0].content == (
        "## First specialtoken\n"
        "First canonical passage.\n"
        "## Second specialtoken\n"
        "Second canonical passage.\n"
    )
    assert result.completeness.returned_count == 1
    assert result.completeness.truncated
    assert result.completeness.more_available
    assert not all_results.completeness.truncated
    assert not all_results.completeness.more_available


def test_read_and_expand_use_canonical_content_without_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loaded_brain: LoadedRepositoryBrain,
) -> None:
    provider = _FakeEmbeddingProvider()
    navigator = _navigator(tmp_path, monkeypatch, loaded_brain, provider)
    context_ref = BridgerRef(
        kind=BridgerRefKind.BRAIN_CONTEXT,
        target_ref={
            "document_id": "collapse-doc",
            "start_line": 2,
            "end_line": 5,
        },
        repository_revision="revision-1",
    )
    statements: list[str] = []
    navigator._connection.set_trace_callback(statements.append)

    exact = navigator.read(IntelligenceReadRequest(ref=context_ref))
    expanded = navigator.expand(context_ref, ReadExpansion.CONTEXT)
    document = navigator.read(
        IntelligenceReadRequest(ref=context_ref, expand=ReadExpansion.DOCUMENT)
    )
    direct_document = navigator.read(IntelligenceReadRequest(ref=document.items[0].ref))

    assert exact.operation is ResultOperation.READ
    assert exact.items[0].content == (
        "## First specialtoken\n"
        "First canonical passage.\n"
        "## Second specialtoken\n"
        "Second canonical passage.\n"
    )
    assert "# Collapse Fixture\n" in (expanded.items[0].content or "")
    assert "## Gap\n" in (expanded.items[0].content or "")
    assert "## Distant specialtoken\n" not in (expanded.items[0].content or "")
    assert document.items[0].kind is BridgerRefKind.BRAIN_DOCUMENT
    assert document.items[0].content == loaded_brain.documents[-1].content
    assert direct_document.items[0] == document.items[0]
    assert provider.query_calls == []
    assert not any("MATCH" in statement.upper() for statement in statements)

    with pytest.raises(NotImplementedError, match="EVIDENCE"):
        navigator.read(
            IntelligenceReadRequest(ref=context_ref, expand=ReadExpansion.EVIDENCE)
        )
    with pytest.raises(ValueError, match="different repository revision"):
        navigator.read(
            IntelligenceReadRequest(
                ref=context_ref.model_copy(
                    update={"repository_revision": "different-revision"}
                )
            )
        )
    with pytest.raises(NotImplementedError, match="BRAIN_CLAIM"):
        navigator.read(
            IntelligenceReadRequest(
                ref=BridgerRef(
                    kind=BridgerRefKind.BRAIN_CLAIM,
                    target_ref={"claim_id": "claim-1"},
                    repository_revision="revision-1",
                )
            )
        )


def _document(
    document_id: str,
    relative_path: str,
    content: str,
    *,
    owner: str,
) -> BrainDocument:
    return BrainDocument(
        document_id=document_id,
        semantic_owner=owner,
        relative_path=relative_path,
        artifact_revision=1,
        digest=f"digest-{document_id}",
        content=content,
    )
