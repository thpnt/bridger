"""Graph-native MCP delegation, output, and error boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp import Client

import bridger.mcp_server as adapter
from bridger.contracts.consumption import (
    GraphCommunity,
    GraphEdge,
    GraphNode,
    UnderstandGraphContext,
)
from bridger.contracts.enrichment import EnrichmentRecord
from bridger.contracts.navigation import (
    CompositeEntityView,
    GraphCommunityView,
    GraphTraversalView,
    RepositorySearchHit,
)
from bridger.navigation.bridger import BridgerNavigator
from bridger.navigation.navigator import GraphQueryResult


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _RepositoryNavigator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.failure: Exception | None = None
        self.node = CompositeEntityView(
            target_type="node",
            target_ref="node-a",
            deterministic={
                "label": "A",
                "source_path": "src/a.py",
                "source_start_line": 2,
                "source_end_line": 4,
            },
            enrichment=[
                EnrichmentRecord(
                    enrichment_id="annotation-a",
                    target_type="node",
                    target_ref="node-a",
                    annotation_type="summary",
                    value="Entry point",
                )
            ],
        )
        self.edge = CompositeEntityView(
            target_type="edge",
            target_ref={
                "source_node_id": "node-a",
                "target_node_id": "node-b",
                "relation": "calls",
            },
            deterministic={
                "source_node_id": "node-a",
                "target_node_id": "node-b",
                "relation": "calls",
            },
        )
        self.hyperedge = CompositeEntityView(
            target_type="hyperedge",
            target_ref="hyperedge-a",
            deterministic={"members": ["node-a", "node-b"]},
        )
        self.community = CompositeEntityView(
            target_type="community",
            target_ref={"community_id": 1, "member_signature": "members-a"},
            deterministic={"label": "Core", "member_count": 2},
        )
        self.query_result = GraphQueryResult(
            context=UnderstandGraphContext(
                seed_node_ids=["node-a"],
                nodes=[
                    GraphNode(
                        node_id="node-a",
                        label="A",
                        source_path="src/a.py",
                        source_start_line=2,
                        source_end_line=4,
                        community_id=1,
                    ),
                    GraphNode(
                        node_id="node-b",
                        label="B",
                        source_path="src/b.py",
                        source_start_line=8,
                        source_end_line=10,
                        community_id=1,
                    ),
                ],
                edges=[
                    GraphEdge(
                        source_node_id="node-a",
                        target_node_id="node-b",
                        relation="calls",
                        evidence_path="src/a.py",
                        evidence_start_line=3,
                        evidence_end_line=3,
                    )
                ],
                communities=[GraphCommunity(community_id=1, label="Core")],
            ),
            truncated=True,
        )
        self.search_result = [
            RepositorySearchHit(
                kind="node",
                ref="node-a",
                label="A",
                source_path="src/a.py",
                score=95,
            )
        ]
        self.traversal_result = GraphTraversalView(
            nodes=[self.node],
            edges=[self.edge],
            hyperedges=[self.hyperedge],
            truncated=True,
        )
        self.community_result = GraphCommunityView(
            community=self.community,
            members=[self.node],
            internal_edges=[self.edge],
            cross_community_edges=[
                CompositeEntityView(
                    target_type="edge",
                    target_ref={
                        "source_node_id": "node-a",
                        "target_node_id": "node-c",
                        "relation": "calls",
                    },
                    deterministic={
                        "source_node_id": "node-a",
                        "target_node_id": "node-c",
                        "relation": "calls",
                    },
                )
            ],
            truncated=True,
        )

    def _record(self, name: str, *args: object, **kwargs: object) -> None:
        self.calls.append((name, args, kwargs))
        if self.failure is not None:
            raise self.failure

    def query_graph(self, query: str) -> GraphQueryResult:
        self._record("query_graph", query)
        return self.query_result

    def search_repository(
        self, query: str, **kwargs: object
    ) -> list[RepositorySearchHit]:
        self._record("search_repository", query, **kwargs)
        return self.search_result

    def get_graph_entity(
        self, target_type: str, target_ref: object, **kwargs: object
    ) -> CompositeEntityView:
        self._record("get_graph_entity", target_type, target_ref, **kwargs)
        return self.node

    def get_graph_neighbors(
        self, node_id: str, **kwargs: object
    ) -> GraphTraversalView:
        self._record("get_graph_neighbors", node_id, **kwargs)
        return self.traversal_result

    def get_graph_subgraph(
        self, node_id: str, **kwargs: object
    ) -> GraphTraversalView:
        self._record("get_graph_subgraph", node_id, **kwargs)
        return self.traversal_result

    def get_graph_path(
        self, source_node_id: str, target_node_id: str, **kwargs: object
    ) -> GraphTraversalView:
        self._record("get_graph_path", source_node_id, target_node_id, **kwargs)
        return self.traversal_result

    def list_graph_communities(
        self, **kwargs: object
    ) -> list[CompositeEntityView]:
        self._record("list_graph_communities", **kwargs)
        return [self.community]

    def get_graph_community(
        self, community_id: int, **kwargs: object
    ) -> GraphCommunityView:
        self._record("get_graph_community", community_id, **kwargs)
        return self.community_result


class _GraphNavigator:
    def __init__(self) -> None:
        self.repository_navigator = _RepositoryNavigator()
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _OpenStateBrain:
    source_identity = ("fixture", "a" * 40, "graph", "overlay")

    def close(self) -> None:
        pass


class _OpenStateRepository:
    source_identity = ("fixture", "a" * 40, "graph", "overlay")


def test_repository_navigator_property_requires_open_owner() -> None:
    repository = _OpenStateRepository()
    navigator = BridgerNavigator(_OpenStateBrain(), repository)  # type: ignore[arg-type]

    assert navigator.repository_navigator is repository

    navigator.close()
    with pytest.raises(RuntimeError, match="BridgerNavigator is closed"):
        _ = navigator.repository_navigator


@pytest.mark.anyio
async def test_graph_tools_delegate_with_structured_results_and_reuse_navigator(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    navigator = _GraphNavigator()
    repository_navigator = navigator.repository_navigator
    loaded: list[Path] = []

    def load(root: Path) -> _GraphNavigator:
        loaded.append(root)
        return navigator

    monkeypatch.setattr(adapter, "load_bridger_navigator", load)
    async with Client(adapter.create_mcp_server(Path("/repo"))) as client:
        query = await client.call_tool("query_graph", {"query": "entry point"})
        assert query.is_error is not True
        assert query.structured_content == {
            "context": navigator.repository_navigator.query_result.context.model_dump(
                mode="json"
            ),
            "truncated": True,
        }
        source_path = query.structured_content["context"]["nodes"][0]["source_path"]
        assert source_path == "src/a.py"

        search = await client.call_tool(
            "search_repository",
            {
                "query": "entry point",
                "kinds": ["node", "community"],
                "limit": 7,
                "min_score": 82,
            },
        )
        assert search.is_error is not True
        assert search.structured_content == [
            hit.model_dump(mode="json")
            for hit in repository_navigator.search_result
        ]

        entity = await client.call_tool(
            "get_graph_entity",
            {
                "target_type": "node",
                "target_ref": "node-a",
                "max_members": 3,
            },
        )
        assert entity.is_error is not True
        assert entity.structured_content == repository_navigator.node.model_dump(
            mode="json"
        )

        neighbors = await client.call_tool(
            "get_graph_neighbors",
            {
                "node_id": "node-a",
                "direction": "incoming",
                "relations": ["calls", "imports"],
                "max_nodes": 4,
                "max_edges": 5,
                "max_hyperedges": 6,
            },
        )
        subgraph = await client.call_tool(
            "get_graph_subgraph",
            {
                "node_id": "node-a",
                "depth": 3,
                "direction": "outgoing",
                "relations": ["calls"],
                "max_nodes": 7,
                "max_edges": 8,
                "max_hyperedges": 9,
            },
        )
        path = await client.call_tool(
            "get_graph_path",
            {
                "source_node_id": "node-a",
                "target_node_id": "node-b",
                "direction": "both",
                "relations": ["calls"],
                "max_depth": 5,
                "max_nodes": 10,
            },
        )
        expected_traversal = repository_navigator.traversal_result.model_dump(
            mode="json"
        )
        for result in (neighbors, subgraph, path):
            assert result.is_error is not True
            assert result.structured_content == expected_traversal
            assert result.structured_content["truncated"] is True

        communities = await client.call_tool(
            "list_graph_communities", {"limit": 9}
        )
        assert communities.is_error is not True
        assert communities.structured_content == [
            repository_navigator.community.model_dump(mode="json")
        ]

        community = await client.call_tool(
            "get_graph_community",
            {"community_id": 1, "max_nodes": 11, "max_edges": 12},
        )
        assert community.is_error is not True
        expected_community = repository_navigator.community_result.model_dump(
            mode="json"
        )
        assert community.structured_content == expected_community
        assert len(loaded) == 1

    assert navigator.close_calls == 1
    assert repository_navigator.calls == [
        ("query_graph", ("entry point",), {}),
        (
            "search_repository",
            ("entry point",),
            {"kinds": ["node", "community"], "limit": 7, "min_score": 82.0},
        ),
        ("get_graph_entity", ("node", "node-a"), {"max_members": 3}),
        (
            "get_graph_neighbors",
            ("node-a",),
            {
                "direction": "incoming",
                "relations": ["calls", "imports"],
                "max_nodes": 4,
                "max_edges": 5,
                "max_hyperedges": 6,
            },
        ),
        (
            "get_graph_subgraph",
            ("node-a",),
            {
                "depth": 3,
                "direction": "outgoing",
                "relations": ["calls"],
                "max_nodes": 7,
                "max_edges": 8,
                "max_hyperedges": 9,
            },
        ),
        (
            "get_graph_path",
            ("node-a", "node-b"),
            {
                "direction": "both",
                "relations": ["calls"],
                "max_depth": 5,
                "max_nodes": 10,
            },
        ),
        ("list_graph_communities", (), {"limit": 9}),
        (
            "get_graph_community",
            (1,),
            {"max_nodes": 11, "max_edges": 12},
        ),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "arguments", "failure"),
    [
        ("query_graph", {"query": ""}, ValueError("query must be non-empty")),
        (
            "get_graph_neighbors",
            {"node_id": "missing"},
            KeyError("unknown graph node: missing"),
        ),
        (
            "get_graph_community",
            {"community_id": 404},
            KeyError("unknown graph community: 404"),
        ),
        (
            "get_graph_path",
            {
                "source_node_id": "node-a",
                "target_node_id": "node-b",
                "direction": "sideways",
            },
            ValueError("direction must be incoming, outgoing, or both"),
        ),
        (
            "get_graph_subgraph",
            {"node_id": "node-a", "depth": 99},
            ValueError("depth must be between 1 and 10"),
        ),
        (
            "get_graph_entity",
            {"target_type": "edge", "target_ref": {"source_node_id": "node-a"}},
            ValueError("edge target_ref requires source, target, and relation"),
        ),
    ],
)
async def test_expected_graph_navigation_errors_are_tool_errors(
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
    arguments: dict[str, object],
    failure: Exception,
) -> None:
    navigator = _GraphNavigator()
    navigator.repository_navigator.failure = failure
    monkeypatch.setattr(adapter, "load_bridger_navigator", lambda _root: navigator)
    async with Client(adapter.create_mcp_server(Path("/repo"))) as client:
        result = await client.call_tool(tool, arguments)
        assert result.is_error is True
        if arguments.get("direction") != "sideways":
            assert str(failure) in result.content[0].text

        navigator.repository_navigator.failure = None
        following = await client.call_tool("query_graph", {"query": "works"})
        assert following.is_error is not True
