"""Focused Layer 4 snapshot lifecycle invariants."""

import subprocess
from copy import deepcopy
from pathlib import Path

import networkx as nx
import pytest

from bridger.contracts.files import (
    FileDisposition,
    FileIndex,
    FileRecord,
    summarize_files,
)
from bridger.contracts.graph import GraphConstructionConfig
from bridger.contracts.repository import RepositoryContext
from bridger.extraction.service import extract_repository_facts
from bridger.graph.errors import FullRebuildRequired, InvalidGraphSnapshot
from bridger.graph.intelligence import build_graph_intelligence
from bridger.graph.lifecycle import (
    create_graph_snapshot,
    load_graph_snapshot,
    load_graph_snapshot_structural_state,
    update_graph_snapshot,
    validate_graph_snapshot,
)
from bridger.repository.revisions import compare_revisions
from bridger.repository.service import prepare_repository


def test_full_snapshot_round_trip_preserves_direction_and_hyperedges(
    tmp_path: Path,
) -> None:
    context, file_index = _context_and_index(tmp_path)
    graph, diagnostics, derived_state = build_graph_intelligence(
        context,
        file_index,
        _extraction(),
        GraphConstructionConfig(),
    )

    output_root = tmp_path / "graph"
    create_graph_snapshot(
        context,
        file_index,
        graph,
        diagnostics,
        derived_state,
        GraphConstructionConfig(),
        output_root,
    )
    del context, file_index, graph, diagnostics, derived_state
    loaded = load_graph_snapshot(output_root)
    structural = load_graph_snapshot_structural_state(loaded)

    assert type(loaded.graph) is nx.DiGraph
    assert list(loaded.graph.edges) == [("a", "b"), ("b", "c")]
    assert list(loaded.graph.successors("a")) == ["b"]
    assert list(loaded.graph.predecessors("b")) == ["a"]
    assert loaded.graph["a"]["b"]["relation"] == "calls"
    assert loaded.graph["a"]["b"]["confidence"] == "EXTRACTED"
    assert loaded.graph["a"]["b"]["weight"] == 1.0
    assert loaded.graph.nodes["a"]["source_file"] == "a.py"
    assert loaded.graph.nodes["a"]["source_location"] == "L1"
    assert nx.shortest_path(loaded.graph, "a", "c") == ["a", "b", "c"]
    assert set(loaded.graph.subgraph(["a", "b"]).nodes) == {"a", "b"}
    assert loaded.graph.graph["hyperedges"] == [
        {"id": "group", "label": "group", "nodes": ["a", "b"]}
    ]
    assert [
        hyperedge["id"]
        for hyperedge in loaded.graph.graph["hyperedges"]
        if "a" in hyperedge["nodes"]
    ] == ["group"]
    assert set(loaded.manifest.artifacts) == {
        "graph.json",
        "structural.json",
        "diagnostics.json",
        "graphify-manifest.json",
        "GRAPH_REPORT.md",
    }
    assert (loaded.snapshot_root / "snapshot-manifest.json").is_file()
    validate_graph_snapshot(loaded.snapshot_root)

    node_communities = {
        node_id: community_id
        for community_id, members in structural["communities"].items()
        for node_id in members
    }
    assert set(node_communities) == set(loaded.graph.nodes)
    for community_id, members in structural["communities"].items():
        assert isinstance(community_id, int)
        assert members
        assert structural["cohesion"][community_id] >= 0
        assert structural["community_member_signatures"][community_id]
        assert structural["community_labels"][community_id]
    assert isinstance(structural["god_nodes"], list)
    assert isinstance(structural["surprising_connections"], list)
    assert isinstance(structural["suggested_questions"], list)

    representative_nodes = sorted(
        loaded.graph.nodes,
        key=lambda node_id: (-loaded.graph.degree(node_id), node_id),
    )
    source_file_distribution = {
        attributes["source_file"] for _, attributes in loaded.graph.nodes(data=True)
    }
    internal_relations = [
        attributes["relation"]
        for source, target, attributes in loaded.graph.edges(data=True)
        if node_communities[source] == node_communities[target]
    ]
    cross_community_relations = [
        attributes["relation"]
        for source, target, attributes in loaded.graph.edges(data=True)
        if node_communities[source] != node_communities[target]
    ]
    assert representative_nodes[0] in {"a", "b"}
    assert source_file_distribution == {"a.py", "b.py", "c.py"}
    assert internal_relations
    assert isinstance(cross_community_relations, list)


def test_corrupt_artifact_is_rejected_and_failed_build_keeps_current(
    tmp_path: Path,
) -> None:
    context, file_index = _context_and_index(tmp_path)
    graph, diagnostics, derived_state = build_graph_intelligence(
        context,
        file_index,
        _extraction(),
        GraphConstructionConfig(),
    )
    output_root = tmp_path / "graph"
    first = create_graph_snapshot(
        context,
        file_index,
        graph,
        diagnostics,
        derived_state,
        GraphConstructionConfig(),
        output_root,
    )
    blocked = diagnostics.model_copy(update={"publication_blocking": True})

    with pytest.raises(InvalidGraphSnapshot, match="publication-blocking"):
        create_graph_snapshot(
            context,
            file_index,
            graph,
            blocked,
            derived_state,
            GraphConstructionConfig(),
            output_root,
        )
    assert (
        load_graph_snapshot(output_root).manifest.snapshot_id
        == first.manifest.snapshot_id
    )

    (first.snapshot_root / "graph.json").write_text("{}", encoding="utf-8")
    with pytest.raises(InvalidGraphSnapshot, match="artifact integrity"):
        load_graph_snapshot(output_root, first.manifest.snapshot_id)


def test_missing_required_artifact_is_rejected(tmp_path: Path) -> None:
    context, file_index = _context_and_index(tmp_path)
    graph, diagnostics, derived_state = build_graph_intelligence(
        context,
        file_index,
        _extraction(),
        GraphConstructionConfig(),
    )
    snapshot = create_graph_snapshot(
        context,
        file_index,
        graph,
        diagnostics,
        derived_state,
        GraphConstructionConfig(),
        tmp_path / "graph",
    )

    (snapshot.snapshot_root / "diagnostics.json").unlink()

    with pytest.raises(InvalidGraphSnapshot, match="required snapshot artifact"):
        validate_graph_snapshot(snapshot.snapshot_root)


def test_incompatible_incremental_update_requires_full_rebuild(tmp_path: Path) -> None:
    context, file_index = _context_and_index(tmp_path)
    graph, diagnostics, derived_state = build_graph_intelligence(
        context,
        file_index,
        _extraction(),
        GraphConstructionConfig(),
    )
    snapshot = create_graph_snapshot(
        context,
        file_index,
        graph,
        diagnostics,
        derived_state,
        GraphConstructionConfig(),
        tmp_path / "graph",
    )
    incompatible = snapshot.manifest.model_copy(
        update={"graphify_engine_version": "incompatible"}
    )

    with pytest.raises(FullRebuildRequired, match="graphify_engine_version"):
        update_graph_snapshot(
            incompatible,
            context,
            file_index,
            _changes(context.revision, context.revision),
            GraphConstructionConfig(),
            tmp_path / "graph",
            parallel=False,
        )


def test_incremental_snapshot_matches_a_clean_full_build(tmp_path: Path) -> None:
    repository = _initialize_repository(tmp_path)
    (repository / "a.py").write_text("def before():\n    return 1\n", encoding="utf-8")
    (repository / "b.py").write_text("def removed():\n    return 2\n", encoding="utf-8")
    _commit(repository)
    initial_context, initial_index = prepare_repository(repository)
    initial_graph, initial_diagnostics, initial_state = _build_from_repository(
        initial_context,
        initial_index,
        tmp_path / "initial-cache",
    )
    output_root = tmp_path / "graph"
    initial = create_graph_snapshot(
        initial_context,
        initial_index,
        initial_graph,
        initial_diagnostics,
        initial_state,
        GraphConstructionConfig(),
        output_root,
    )

    (repository / "a.py").write_text("def after():\n    return 3\n", encoding="utf-8")
    (repository / "b.py").unlink()
    _commit(repository)
    target_context, target_index = prepare_repository(repository)
    changes = compare_revisions(
        target_context,
        initial_context.revision,
        target_context.revision,
    )

    incremental = update_graph_snapshot(
        initial.manifest,
        target_context,
        target_index,
        changes,
        GraphConstructionConfig(),
        output_root,
        cache_root=tmp_path / "incremental-cache",
        parallel=False,
    )
    full_graph, full_diagnostics, _full_state = _build_from_repository(
        target_context,
        target_index,
        tmp_path / "full-cache",
    )

    assert incremental.manifest.build_mode == "incremental"
    assert incremental.manifest.parent_snapshot_id == initial.manifest.snapshot_id
    assert incremental.diagnostics.publication_blocking is False
    assert _graph_topology(incremental.graph) == _graph_topology(full_graph)
    assert "b.py" not in {
        attributes.get("source_file")
        for _, attributes in incremental.graph.nodes(data=True)
    }
    assert initial.manifest.snapshot_id != incremental.manifest.snapshot_id
    assert full_diagnostics.publication_blocking is False


def _build_from_repository(
    context: RepositoryContext,
    file_index: FileIndex,
    cache_root: Path,
) -> tuple[nx.DiGraph, object, dict[str, object]]:
    _symbols, _report, extraction = extract_repository_facts(
        context,
        file_index,
        cache_root=cache_root,
        parallel=False,
    )
    return build_graph_intelligence(
        context,
        file_index,
        extraction,
        GraphConstructionConfig(),
    )


def _graph_topology(graph: nx.DiGraph) -> tuple[set[str], set[tuple[str, str, str]]]:
    return (
        set(graph.nodes),
        {
            (source, target, str(attributes.get("relation")))
            for source, target, attributes in graph.edges(data=True)
        },
    )


def _context_and_index(tmp_path: Path) -> tuple[RepositoryContext, FileIndex]:
    repository = tmp_path / "repository"
    repository.mkdir()
    records: list[FileRecord] = []
    for path in ("a.py", "b.py", "c.py"):
        (repository / path).write_text("pass\n", encoding="utf-8")
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
        root_path=repository,
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
                _edge("b", "c", "calls"),
            ],
            "hyperedges": [{"id": "group", "label": "group", "nodes": ["a", "b"]}],
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
        "weight": 1.0,
        "source_file": "a.py",
        "_origin": "ast",
    }


def _changes(base_revision: str, target_revision: str):
    from bridger.contracts.files import FileChangeSet

    return FileChangeSet(
        base_revision=base_revision,
        target_revision=target_revision,
    )


def _initialize_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "git-repository"
    repository.mkdir()
    _run_git(repository, "init")
    _run_git(repository, "config", "user.email", "test@example.com")
    _run_git(repository, "config", "user.name", "Test User")
    return repository


def _commit(repository: Path) -> None:
    _run_git(repository, "add", ".")
    _run_git(repository, "commit", "-m", "test")


def _run_git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
    )
