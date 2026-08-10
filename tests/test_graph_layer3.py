"""Focused Layer 3 graph construction invariants."""

import sys
from copy import deepcopy
from pathlib import Path

import networkx as nx
import pytest
from pydantic import ValidationError

from graph.intelligence import build_graph_intelligence
from graphify import cluster as graphify_cluster
from models.files import FileDisposition, FileIndex, FileRecord, summarize_files
from models.graph import GraphConstructionConfig
from models.repository import RepositoryContext


def test_builds_directed_graph_and_reports_same_endpoint_collapse(
    tmp_path: Path,
) -> None:
    context, file_index = _context_and_file_index(tmp_path)

    graph, diagnostics, derived_state = build_graph_intelligence(
        context,
        file_index,
        _extraction(),
        GraphConstructionConfig(),
    )

    assert type(graph) is nx.DiGraph
    assert graph.number_of_edges() == 2
    assert diagnostics.input_edge_count == 3
    assert diagnostics.output_edge_count == 2
    assert diagnostics.possible_same_endpoint_edge_collapse_count == 1
    assert diagnostics.severity == "warning"
    assert not diagnostics.publication_blocking
    assert set(derived_state) == {
        "communities",
        "cohesion",
        "community_member_signatures",
        "community_labels",
        "god_nodes",
        "surprising_connections",
        "suggested_questions",
    }
    assert diagnostics.community_coverage_complete


def test_community_derivation_is_deterministic(tmp_path: Path) -> None:
    context, file_index = _context_and_file_index(tmp_path)
    config = GraphConstructionConfig()

    _, first_diagnostics, first_state = build_graph_intelligence(
        context,
        file_index,
        _extraction(),
        config,
    )
    _, second_diagnostics, second_state = build_graph_intelligence(
        context,
        file_index,
        _extraction(),
        config,
    )

    assert first_diagnostics == second_diagnostics
    assert first_state["communities"] == second_state["communities"]
    assert first_state["cohesion"] == second_state["cohesion"]
    assert (
        first_state["community_member_signatures"]
        == second_state["community_member_signatures"]
    )
    assert first_state["community_labels"] == second_state["community_labels"]


def test_missing_leiden_runtime_fails_without_louvain_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = nx.Graph()
    graph.add_edge("a", "b")
    monkeypatch.delitem(sys.modules, "graspologic.partition", raising=False)
    monkeypatch.setitem(sys.modules, "graspologic", None)

    with pytest.raises(RuntimeError, match="requires the graspologic"):
        graphify_cluster._partition(graph)


def test_invalid_repository_source_path_blocks_publication(tmp_path: Path) -> None:
    context, file_index = _context_and_file_index(tmp_path)
    extraction = _extraction()
    extraction["nodes"][0]["source_file"] = "missing.py"

    _, diagnostics, _ = build_graph_intelligence(
        context,
        file_index,
        extraction,
        GraphConstructionConfig(),
    )

    assert diagnostics.publication_blocking
    assert diagnostics.severity == "error"
    assert diagnostics.file_index_consistency_failures == [
        "node 'a' claims source_file absent from FileIndex: missing.py"
    ]


def test_only_leiden_is_a_valid_community_algorithm() -> None:
    with pytest.raises(ValidationError):
        GraphConstructionConfig(community_algorithm="louvain")


def _context_and_file_index(tmp_path: Path) -> tuple[RepositoryContext, FileIndex]:
    root_path = tmp_path / "repository"
    root_path.mkdir()
    records = []
    for path in ("a.py", "b.py", "c.py"):
        (root_path / path).write_text("pass\n", encoding="utf-8")
        records.append(
            FileRecord(
                path=path,
                git_object_id="a" * 40,
                size_bytes=5,
                content_type="source",
                language="python",
                disposition=FileDisposition(
                    read_mode="full",
                    processing_mode="extract",
                ),
            )
        )
    context = RepositoryContext(
        repository_id="test-repository",
        root_path=root_path,
        revision="b" * 40,
    )
    return context, FileIndex(
        schema_version="1",
        repository_id=context.repository_id,
        revision=context.revision,
        scope_path=context.scope_path,
        files=records,
        summary=summarize_files(records),
    )


def _extraction() -> dict[str, object]:
    return deepcopy(
        {
            "nodes": [
                _node("a", "a.py"),
                _node("b", "b.py"),
                _node("c", "c.py"),
            ],
            "edges": [
                _edge("a", "b", "calls"),
                _edge("a", "b", "uses"),
                _edge("b", "c", "calls"),
            ],
            "hyperedges": [],
        }
    )


def _node(node_id: str, source_file: str) -> dict[str, str]:
    return {
        "id": node_id,
        "label": node_id,
        "file_type": "code",
        "source_file": source_file,
        "source_location": "L1",
        "_origin": "ast",
    }


def _edge(source: str, target: str, relation: str) -> dict[str, str]:
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "confidence": "EXTRACTED",
        "source_file": "a.py",
        "_origin": "ast",
    }
