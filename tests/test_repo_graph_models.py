from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bridger.models.graph_summary import GraphSummaryArtifact, GraphSummaryCounts
from bridger.models.repo_graph import (
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    RepoGraphArtifact,
)


def test_valid_minimal_repo_graph_passes_validation() -> None:
    artifact = RepoGraphArtifact(
        generated_at=datetime(2026, 6, 19, tzinfo=UTC),
        nodes=[GraphNode(id="file:main.py", kind=GraphNodeKind.FILE, path="main.py")],
    )

    assert artifact.schema_version == 1


def test_graph_node_rejects_absolute_path() -> None:
    with pytest.raises(ValidationError):
        GraphNode(id="file:/main.py", kind=GraphNodeKind.FILE, path="/main.py")


def test_invalid_node_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GraphNode.model_validate({"id": "file:main.py", "kind": "service"})


def test_invalid_edge_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GraphEdge.model_validate(
            {"from": "file:a.py", "to": "file:b.py", "kind": "owns"}
        )


def test_graph_edge_uses_contract_aliases() -> None:
    edge = GraphEdge(
        from_id="file:a.py",
        to_id="file:b.py",
        kind=GraphEdgeKind.IMPORTS,
    )

    assert edge.model_dump(by_alias=True)["from"] == "file:a.py"


def test_valid_minimal_graph_summary_passes_validation() -> None:
    artifact = GraphSummaryArtifact(
        generated_at=datetime(2026, 6, 19, tzinfo=UTC),
        counts=GraphSummaryCounts(),
    )

    assert artifact.schema_version == 1
