"""Focused routing and composition tests for BridgerNavigator V0."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from bridger.contracts._legacy_consumption import (
    Authority,
    BridgerRef,
    BridgerRefKind,
    Completeness,
    IntelligenceItem,
    IntelligenceQueryRequest,
    IntelligenceReadRequest,
    IntelligenceResult,
    Lens,
    Provenance,
    ResultOperation,
    ScopeKind,
    ScopeRef,
    Substrate,
)
from bridger.contracts.files import FileDisposition, FileRecord, SourceReadResult
from bridger.contracts.navigation import (
    CompositeEntityView,
    FileOverview,
    GraphTraversalView,
)
from bridger.navigation import BridgerNavigator

REVISION = "a" * 40


def _brain_item(index: int) -> IntelligenceItem:
    ref = BridgerRef(
        kind=BridgerRefKind.BRAIN_CONTEXT,
        target_ref={"document_id": f"brain-{index}", "start_line": 1, "end_line": 1},
        repository_revision=REVISION,
    )
    return IntelligenceItem(
        ref=ref,
        kind=ref.kind,
        title=f"brain-{index}",
        content=f"brain content {index}",
        provenance=Provenance(
            repository_revision=REVISION,
            substrate=Substrate.BRAIN,
            authority=Authority.DERIVED,
        ),
    )


@dataclass
class _FakeBrain:
    repository_revision: str = REVISION
    search_calls: list[IntelligenceQueryRequest] = field(default_factory=list)
    read_calls: list[IntelligenceReadRequest] = field(default_factory=list)
    truncated: bool = False
    close_calls: int = 0

    def close(self) -> None:
        self.close_calls += 1

    def search(self, request: IntelligenceQueryRequest) -> IntelligenceResult:
        self.search_calls.append(request)
        limit = request.limit or 5
        items = [_brain_item(index) for index in range(limit)]
        return IntelligenceResult(
            operation=ResultOperation.QUERY,
            repository_revision=REVISION,
            lens=request.lens,
            query=request.query,
            scope=request.scope,
            items=items,
            completeness=Completeness(
                returned_count=len(items),
                truncated=self.truncated,
                more_available=self.truncated,
            ),
        )

    def read(self, request: IntelligenceReadRequest) -> IntelligenceResult:
        self.read_calls.append(request)
        item = _brain_item(0).model_copy(update={"ref": request.ref})
        return IntelligenceResult(
            operation=ResultOperation.READ,
            repository_revision=REVISION,
            items=[item],
            completeness=Completeness(returned_count=1),
        )


class _FakeRepository:
    source_identity = ("repository", REVISION, "snapshot", None)

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.truncated_seed: str | None = None
        self.empty_file_mapping = False

    def get_graph_entity(
        self, target_type: str, target_ref: object, **_kwargs: object
    ) -> CompositeEntityView:
        self.calls.append(("get_graph_entity", (target_type, target_ref)))
        deterministic: dict[str, object] = {"deterministic_label": str(target_ref)}
        if target_type == "node":
            deterministic = {"attributes": {"label": str(target_ref)}}
        elif target_type == "edge":
            assert isinstance(target_ref, dict)
            deterministic = {
                "source_node_id": target_ref["source_node_id"],
                "target_node_id": target_ref["target_node_id"],
            }
        elif target_type == "hyperedge":
            deterministic = {"nodes": ["seed-a", "seed-b"], "members_truncated": False}
        elif target_type == "community":
            deterministic = {
                "members": ["seed-a", "seed-b"],
                "members_truncated": False,
            }
        return CompositeEntityView(
            target_type=target_type,  # type: ignore[arg-type]
            target_ref=target_ref,  # type: ignore[arg-type]
            deterministic=deterministic,  # type: ignore[arg-type]
        )

    def list_graph_communities(self, *, limit: int) -> list[CompositeEntityView]:
        self.calls.append(("list_graph_communities", limit))
        return [
            self.get_graph_entity("community", {"community_id": index})
            for index in range(2)
        ]

    def get_graph_central_nodes(self, *, limit: int) -> list[CompositeEntityView]:
        self.calls.append(("get_graph_central_nodes", limit))
        return [self.get_graph_entity("node", f"central-{index}") for index in range(2)]

    def get_file_overview(self, path: str) -> FileOverview:
        self.calls.append(("get_file_overview", path))
        return FileOverview(
            file=FileRecord(
                path=path,
                git_object_id="b" * 40,
                size_bytes=1,
                content_type="source",
                disposition=FileDisposition(
                    read_mode="full", processing_mode="extract"
                ),
            ),
            symbol_ids=["symbol-a"],
            graph_node_ids=["file-node"],
        )

    def read_symbol_excerpt(self, symbol_id: str) -> SourceReadResult:
        self.calls.append(("read_symbol_excerpt", symbol_id))
        return SourceReadResult(
            path="src/module.py",
            revision=REVISION,
            content=f"def {symbol_id}(): pass\n",
            start_line=1,
            end_line=1,
            content_digest="c" * 64,
            encoding="utf-8",
            truncated=False,
        )

    def symbol_to_graph(self, symbol_id: str) -> list[str]:
        self.calls.append(("symbol_to_graph", symbol_id))
        return ["symbol-node"]

    def file_to_graph(self, path: str) -> list[str]:
        self.calls.append(("file_to_graph", path))
        return [] if self.empty_file_mapping else ["file-seed", "other-seed"]

    def get_graph_subgraph(
        self, seed: str, *, direction: str, depth: int
    ) -> GraphTraversalView:
        self.calls.append(("get_graph_subgraph", (seed, direction, depth)))
        nodes = [
            self.get_graph_entity("node", seed),
            self.get_graph_entity("node", "shared"),
        ]
        return GraphTraversalView(
            nodes=nodes,
            truncated=seed == self.truncated_seed,
        )


def _navigator() -> tuple[BridgerNavigator, _FakeBrain, _FakeRepository]:
    brain = _FakeBrain()
    repository = _FakeRepository()
    return BridgerNavigator(brain, repository), brain, repository  # type: ignore[arg-type]


def _graph_ref(kind: BridgerRefKind = BridgerRefKind.NODE) -> BridgerRef:
    target: object = "node-a"
    if kind is BridgerRefKind.EDGE:
        target = {
            "source_node_id": "source",
            "target_node_id": "target",
            "relation": "calls",
        }
    if kind is BridgerRefKind.COMMUNITY:
        target = {"community_id": 1}
    return BridgerRef(
        kind=kind,
        target_ref=target,  # type: ignore[arg-type]
        repository_revision=REVISION,
    )


def test_close_delegates_to_owned_brain_and_is_idempotent() -> None:
    navigator, brain, _repository = _navigator()

    navigator.close()
    navigator.close()

    assert brain.close_calls == 2


def test_context_manager_returns_self_closes_brain_and_propagates_exception() -> None:
    navigator, brain, _repository = _navigator()

    with pytest.raises(RuntimeError, match="boom"):
        with navigator as entered:
            assert entered is navigator
            result = navigator.query(
                IntelligenceQueryRequest(lens=Lens.GUARDRAILS, query="find")
            )
            assert result.items
            raise RuntimeError("boom")

    assert brain.close_calls == 1


@pytest.mark.parametrize(
    ("query_request", "repository_call"),
    [
        (IntelligenceQueryRequest(lens=Lens.UNDERSTAND, query="find"), None),
        (
            IntelligenceQueryRequest(
                lens=Lens.UNDERSTAND,
                scope=ScopeRef(
                    kind=ScopeKind.BRAIN_REF,
                    value=BridgerRef(
                        kind=BridgerRefKind.BRAIN_CONTEXT,
                        target_ref={
                            "document_id": "brain-0",
                            "start_line": 1,
                            "end_line": 1,
                        },
                        repository_revision=REVISION,
                    ),
                ),
            ),
            None,
        ),
        (
            IntelligenceQueryRequest(
                lens=Lens.UNDERSTAND,
                query="find",
                scope=ScopeRef(kind=ScopeKind.REPOSITORY),
            ),
            "get_graph_entity",
        ),
        (
            IntelligenceQueryRequest(
                lens=Lens.UNDERSTAND,
                query="find",
                scope=ScopeRef(kind=ScopeKind.PATH, value="src/module.py"),
            ),
            "get_file_overview",
        ),
        (
            IntelligenceQueryRequest(
                lens=Lens.UNDERSTAND,
                query="find",
                scope=ScopeRef(kind=ScopeKind.SYMBOL, value="symbol-a"),
            ),
            "read_symbol_excerpt",
        ),
        (
            IntelligenceQueryRequest(
                lens=Lens.UNDERSTAND,
                query="find",
                scope=ScopeRef(kind=ScopeKind.GRAPH_ENTITY, value=_graph_ref()),
            ),
            "get_graph_entity",
        ),
    ],
)
def test_understand_routing_matrix(
    query_request: IntelligenceQueryRequest, repository_call: str | None
) -> None:
    navigator, brain, repository = _navigator()

    result = navigator.query(query_request)

    assert len(brain.search_calls) == 1
    if repository_call is None:
        assert repository.calls == []
    else:
        assert any(name == repository_call for name, _value in repository.calls)
    assert result.items[0].kind is BridgerRefKind.BRAIN_CONTEXT


def test_guardrails_uses_brain_only() -> None:
    navigator, brain, repository = _navigator()

    navigator.query(IntelligenceQueryRequest(lens=Lens.GUARDRAILS, query="rules"))

    assert len(brain.search_calls) == 1
    assert repository.calls == []


def test_impact_uses_incoming_depth_two_and_deduplicates_multiple_seeds() -> None:
    navigator, brain, repository = _navigator()
    repository.truncated_seed = "file-seed"

    result = navigator.query(
        IntelligenceQueryRequest(
            lens=Lens.IMPACT,
            query="impact",
            scope=ScopeRef(kind=ScopeKind.PATH, value="src/module.py"),
            limit=6,
        )
    )

    assert [call for call in repository.calls if call[0] == "get_graph_subgraph"] == [
        ("get_graph_subgraph", ("file-seed", "incoming", 2)),
        ("get_graph_subgraph", ("other-seed", "incoming", 2)),
    ]
    assert [item.ref.target_ref for item in result.items[:3]] == [
        "file-seed",
        "shared",
        "other-seed",
    ]
    assert result.items[0].provenance.substrate is Substrate.DETERMINISTIC_GRAPH
    assert result.completeness.truncated
    assert result.completeness.more_available
    assert len(brain.search_calls) == 1


@pytest.mark.parametrize(
    "kind",
    [
        BridgerRefKind.NODE,
        BridgerRefKind.EDGE,
        BridgerRefKind.HYPEREDGE,
        BridgerRefKind.COMMUNITY,
    ],
)
def test_impact_resolves_each_graph_scope_kind(kind: BridgerRefKind) -> None:
    navigator, _brain, repository = _navigator()

    navigator.query(
        IntelligenceQueryRequest(
            lens=Lens.IMPACT,
            scope=ScopeRef(kind=ScopeKind.GRAPH_ENTITY, value=_graph_ref(kind)),
        )
    )

    assert any(name == "get_graph_subgraph" for name, _value in repository.calls)


def test_impact_rejects_graph_wide_scope_and_missing_seed() -> None:
    navigator, _brain, repository = _navigator()
    with pytest.raises(ValueError, match="too broad"):
        navigator.query(
            IntelligenceQueryRequest(
                lens=Lens.IMPACT,
                scope=ScopeRef(
                    kind=ScopeKind.GRAPH_ENTITY,
                    value=_graph_ref(BridgerRefKind.GRAPH),
                ),
            )
        )

    repository.empty_file_mapping = True
    with pytest.raises(ValueError, match="no graph association"):
        navigator.query(
            IntelligenceQueryRequest(
                lens=Lens.IMPACT,
                scope=ScopeRef(kind=ScopeKind.PATH, value="src/module.py"),
            )
        )


def test_composition_enforces_budget_reallocates_and_preserves_primary_order() -> None:
    navigator, _brain, _repository = _navigator()

    understand = navigator.query(
        IntelligenceQueryRequest(
            lens=Lens.UNDERSTAND,
            query="find",
            scope=ScopeRef(kind=ScopeKind.PATH, value="src/module.py"),
            limit=6,
        )
    )
    impact = navigator.query(
        IntelligenceQueryRequest(
            lens=Lens.IMPACT,
            scope=ScopeRef(kind=ScopeKind.PATH, value="src/module.py"),
            limit=6,
        )
    )

    assert [item.kind for item in understand.items] == [
        BridgerRefKind.BRAIN_CONTEXT,
        BridgerRefKind.BRAIN_CONTEXT,
        BridgerRefKind.BRAIN_CONTEXT,
        BridgerRefKind.BRAIN_CONTEXT,
        BridgerRefKind.BRAIN_CONTEXT,
        BridgerRefKind.FILE,
    ]
    assert len(impact.items) == 6
    assert all(item.kind is BridgerRefKind.NODE for item in impact.items[:3])
    assert all(item.kind is BridgerRefKind.BRAIN_CONTEXT for item in impact.items[3:])
    assert understand.completeness.truncated
    assert understand.completeness.more_available


def test_normalization_completeness_and_read_routing() -> None:
    navigator, brain, repository = _navigator()
    queried = navigator.query(
        IntelligenceQueryRequest(
            lens=Lens.UNDERSTAND,
            query="find",
            scope=ScopeRef(kind=ScopeKind.PATH, value="src/module.py"),
            limit=6,
        )
    )
    file_item = queried.items[-1]
    symbol_ref = BridgerRef(
        kind=BridgerRefKind.SYMBOL,
        target_ref="symbol-a",
        repository_revision=REVISION,
    )
    graph_ref = _graph_ref()

    symbol = navigator.read(IntelligenceReadRequest(ref=symbol_ref))
    graph = navigator.read(IntelligenceReadRequest(ref=graph_ref))
    file = navigator.read(IntelligenceReadRequest(ref=file_item.ref))
    brain_result = navigator.read(IntelligenceReadRequest(ref=_brain_item(0).ref))

    assert file_item.data is not None
    assert file_item.content is None
    assert symbol.items[0].content == "def symbol-a(): pass\n"
    assert symbol.items[0].data is not None
    assert graph.items[0].data is not None
    assert file.items[0].related_refs[0].kind is BridgerRefKind.SYMBOL
    assert len(brain.search_calls) == 1
    assert len(brain.read_calls) == 1
    assert brain_result.items[0].kind is BridgerRefKind.BRAIN_CONTEXT
    assert all(
        item.ref.repository_revision == item.provenance.repository_revision == REVISION
        for item in [*symbol.items, *graph.items, *file.items]
    )


def test_revisions_expansions_and_required_failures_are_rejected() -> None:
    brain = _FakeBrain(repository_revision="b" * 40)
    with pytest.raises(ValueError, match="different revisions"):
        BridgerNavigator(brain, _FakeRepository())  # type: ignore[arg-type]
    assert brain.close_calls == 0

    navigator, _brain, _repository = _navigator()
    with pytest.raises(ValueError, match="different repository revision"):
        navigator.read(
            IntelligenceReadRequest(
                ref=_graph_ref().model_copy(update={"repository_revision": "b" * 40})
            )
        )
    with pytest.raises(ValueError, match="expansions"):
        navigator.read(
            IntelligenceReadRequest(
                ref=_graph_ref(),
                expand="context",  # type: ignore[arg-type]
            )
        )
    with pytest.raises(NotImplementedError, match="EVIDENCE"):
        navigator.read(
            IntelligenceReadRequest(
                ref=BridgerRef(
                    kind=BridgerRefKind.EVIDENCE,
                    target_ref="evidence",
                    repository_revision=REVISION,
                )
            )
        )
