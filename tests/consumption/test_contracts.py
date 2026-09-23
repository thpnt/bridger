"""Focused validation tests for the simplified V0 consumption contracts."""

import pytest
from pydantic import BaseModel, ValidationError

from bridger.contracts import (
    BrainContext,
    Completeness,
    ConsumptionRevision,
    GraphCommunity,
    GraphEdge,
    GraphNode,
    ImpactGraph,
    ImpactNode,
    ImpactResolutionIssue,
    ImpactResult,
    ResolvedImpactRoot,
    SymbolRecord,
    UnderstandGraphContext,
    UnderstandResult,
)

REVISION = "a" * 40


def _revision() -> ConsumptionRevision:
    return ConsumptionRevision(
        repository_id="repository-1",
        repository_revision=REVISION,
        graph_snapshot_id="snapshot-1",
        enrichment_overlay_id="overlay-1",
    )


def _brain_context() -> BrainContext:
    return BrainContext(
        path="brain/architecture.md",
        heading="Retry lifecycle",
        start_line=2,
        end_line=4,
        excerpt="Retries are bounded and idempotent.",
        semantic_owner="business-logic",
    )


def _node(node_id: str = "node-1", *, community_id: int | None = 1) -> GraphNode:
    return GraphNode(
        node_id=node_id,
        label=node_id,
        symbol_ids=["symbol-1"],
        source_path="src/retry.py",
        source_start_line=10,
        source_end_line=12,
        community_id=community_id,
    )


def _edge(target_node_id: str = "node-2") -> GraphEdge:
    return GraphEdge(
        source_node_id="node-1",
        target_node_id=target_node_id,
        relation="calls",
        evidence="The scheduler calls the retry worker.",
        evidence_path="src/retry.py",
        evidence_start_line=10,
        evidence_end_line=12,
    )


def _symbol() -> SymbolRecord:
    return SymbolRecord(
        symbol_id="symbol-1",
        name="retry",
        qualified_name="webhooks.retry",
        kind="function",
        path="src/retry.py",
        start_line=10,
        end_line=12,
    )


def _impact_graph() -> ImpactGraph:
    return ImpactGraph(
        nodes=[
            ImpactNode(**_node().model_dump(), depth=0),
            ImpactNode(**_node("node-2", community_id=None).model_dump(), depth=1),
        ],
        edges=[_edge()],
        communities=[GraphCommunity(community_id=1, label="Retry processing")],
        important_node_ids=["node-1"],
    )


def _successful_impact() -> ImpactResult:
    return ImpactResult(
        revision=_revision(),
        requested_symbols=["symbol-1"],
        resolved_roots=[
            ResolvedImpactRoot(
                selector="symbol-1",
                graph_node_ids=["node-1"],
                symbol=_symbol(),
            )
        ],
        affected_graph=_impact_graph(),
        brain_enrichment=[_brain_context()],
        completeness=Completeness(),
    )


def test_consumption_revision_accepts_git_revision_and_rejects_invalid_values() -> None:
    assert _revision().repository_revision == REVISION

    for value in ["a" * 39, "g" * 40, "A" * 40]:
        with pytest.raises(ValidationError):
            ConsumptionRevision(
                repository_id="repository-1",
                repository_revision=value,
                graph_snapshot_id="snapshot-1",
                enrichment_overlay_id="overlay-1",
            )


def test_brain_context_validates_line_ranges() -> None:
    assert _brain_context().start_line == 2

    with pytest.raises(ValidationError):
        BrainContext(
            path="brain/architecture.md",
            start_line=4,
            end_line=2,
            excerpt="text",
            semantic_owner="business-logic",
        )


def test_graph_node_validates_source_range_consistency() -> None:
    assert _node().source_path == "src/retry.py"

    invalid_nodes = [
        _node().model_dump(exclude={"source_end_line"}),
        _node()
        .model_copy(update={"source_start_line": 12, "source_end_line": 10})
        .model_dump(),
        _node().model_copy(update={"source_path": None}).model_dump(),
    ]
    for node in invalid_nodes:
        with pytest.raises(ValidationError):
            GraphNode.model_validate(node)


def test_graph_edge_validates_evidence_range_consistency() -> None:
    assert _edge().evidence_path == "src/retry.py"

    invalid_edges = [
        _edge().model_dump(exclude={"evidence_end_line"}),
        _edge()
        .model_copy(update={"evidence_start_line": 12, "evidence_end_line": 10})
        .model_dump(),
        _edge().model_copy(update={"evidence_path": None}).model_dump(),
    ]
    for edge in invalid_edges:
        with pytest.raises(ValidationError):
            GraphEdge.model_validate(edge)


def test_understand_graph_context_validates_references() -> None:
    context = UnderstandGraphContext(
        seed_node_ids=["node-1"],
        nodes=[_node(), _node("node-2", community_id=None)],
        edges=[_edge()],
        communities=[GraphCommunity(community_id=1, label="Retry processing")],
    )
    assert context.seed_node_ids == ["node-1"]

    invalid_contexts = [
        context.model_copy(update={"seed_node_ids": ["missing"]}),
        context.model_copy(update={"edges": [_edge("missing")]}),
        context.model_copy(
            update={
                "nodes": [
                    _node("node-1", community_id=2),
                    _node("node-2", community_id=None),
                ]
            }
        ),
    ]
    for invalid_context in invalid_contexts:
        with pytest.raises(ValidationError):
            UnderstandGraphContext.model_validate(invalid_context.model_dump())


def test_understand_result_contains_independent_evidence_channels() -> None:
    result = UnderstandResult(
        query="retry behavior",
        revision=_revision(),
        brain_context=[_brain_context()],
        graph_context=UnderstandGraphContext(
            seed_node_ids=["node-1"],
            nodes=[_node()],
            communities=[GraphCommunity(community_id=1, label="Retry processing")],
        ),
        completeness=Completeness(brain_truncated=True),
        warnings=["dense retrieval unavailable"],
    )

    assert result.brain_context and result.graph_context.nodes
    assert result.completeness.graph_truncated is False


def test_impact_result_accepts_successful_resolution() -> None:
    result = _successful_impact()

    assert result.affected_graph is not None
    assert result.resolved_roots[0].symbol == _symbol()


def test_impact_result_accepts_resolution_failure() -> None:
    result = ImpactResult(
        revision=_revision(),
        requested_symbols=["Retry"],
        resolution_issues=[
            ImpactResolutionIssue(selector="Retry", reason="ambiguous", candidates=[])
        ],
        completeness=Completeness(),
    )

    assert result.affected_graph is None
    assert result.resolution_issues[0].reason == "ambiguous"


@pytest.mark.parametrize(
    "field",
    ["affected_graph", "brain_enrichment"],
)
def test_impact_resolution_failure_rejects_follow_up_results(field: str) -> None:
    values: dict[str, object] = {
        "revision": _revision(),
        "requested_symbols": ["missing"],
        "resolution_issues": [
            ImpactResolutionIssue(selector="missing", reason="not_found")
        ],
        "completeness": Completeness(),
    }
    values[field] = _impact_graph() if field == "affected_graph" else [_brain_context()]

    with pytest.raises(ValidationError):
        ImpactResult(**values)


def test_successful_impact_requires_affected_graph() -> None:
    with pytest.raises(ValidationError):
        ImpactResult(
            revision=_revision(),
            requested_symbols=["symbol-1"],
            resolved_roots=[
                ResolvedImpactRoot(selector="symbol-1", graph_node_ids=["node-1"])
            ],
            completeness=Completeness(),
        )


def test_impact_graph_validates_edges_important_nodes_and_communities() -> None:
    graph = _impact_graph()
    assert graph.important_node_ids == ["node-1"]

    invalid_graphs = [
        graph.model_copy(update={"edges": [_edge("missing")]}),
        graph.model_copy(update={"important_node_ids": ["missing"]}),
        graph.model_copy(
            update={
                "nodes": [
                    ImpactNode(**_node("node-1", community_id=2).model_dump(), depth=0),
                    ImpactNode(
                        **_node("node-2", community_id=None).model_dump(), depth=1
                    ),
                ]
            }
        ),
    ]
    for invalid_graph in invalid_graphs:
        with pytest.raises(ValidationError):
            ImpactGraph.model_validate(invalid_graph.model_dump())


def test_unknown_fields_are_rejected_by_all_new_models() -> None:
    models: list[BaseModel] = [
        _revision(),
        Completeness(),
        _brain_context(),
        _node(),
        _edge(),
        GraphCommunity(community_id=1, label="Retry processing"),
        UnderstandGraphContext(),
        UnderstandResult(
            query="retry",
            revision=_revision(),
            graph_context=UnderstandGraphContext(),
            completeness=Completeness(),
        ),
        ResolvedImpactRoot(selector="node-1", graph_node_ids=["node-1"]),
        ImpactResolutionIssue(selector="missing", reason="not_found"),
        ImpactNode(**_node().model_dump(), depth=0),
        _impact_graph(),
        _successful_impact(),
    ]

    for model in models:
        with pytest.raises(ValidationError):
            type(model).model_validate({**model.model_dump(), "unexpected": True})
