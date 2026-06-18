from datetime import UTC, datetime

from bridger.deterministic.graph_summary import build_graph_summary
from bridger.deterministic.graph_summary.builder import (
    UNRESOLVED_IMPORT_SAMPLE_LIMIT,
)
from bridger.models.repo_graph import (
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    RepoGraphArtifact,
    RepoGraphUnresolvedImport,
)


def make_graph() -> RepoGraphArtifact:
    nodes = [
        GraphNode(id="dir:.", kind=GraphNodeKind.DIRECTORY, path="."),
        GraphNode(id="file:a.py", kind=GraphNodeKind.FILE, path="a.py"),
        GraphNode(id="file:b.py", kind=GraphNodeKind.FILE, path="b.py"),
        GraphNode(id="file:c.py", kind=GraphNodeKind.FILE, path="c.py"),
        GraphNode(
            id="manifest:pyproject.toml:project.scripts.app",
            kind=GraphNodeKind.MANIFEST_ENTRY,
            path="pyproject.toml",
            key="project.scripts.app",
        ),
    ]
    edges = [
        GraphEdge(from_id="dir:.", to_id="file:a.py", kind=GraphEdgeKind.CONTAINS),
        GraphEdge(from_id="dir:.", to_id="file:b.py", kind=GraphEdgeKind.CONTAINS),
        GraphEdge(from_id="file:a.py", to_id="file:b.py", kind=GraphEdgeKind.IMPORTS),
        GraphEdge(from_id="file:c.py", to_id="file:b.py", kind=GraphEdgeKind.IMPORTS),
        GraphEdge(from_id="file:a.py", to_id="file:c.py", kind=GraphEdgeKind.IMPORTS),
        GraphEdge(
            from_id="manifest:pyproject.toml:project.scripts.app",
            to_id="file:a.py",
            kind=GraphEdgeKind.DECLARES_ENTRYPOINT,
        ),
    ]
    unresolved = [
        RepoGraphUnresolvedImport(
            from_path="a.py",
            import_text=f"from . import missing_{index}",
            reason="no_matching_file",
        )
        for index in range(UNRESOLVED_IMPORT_SAMPLE_LIMIT + 2)
    ]
    return RepoGraphArtifact(
        generated_at=datetime(2026, 6, 19, tzinfo=UTC),
        nodes=nodes,
        edges=edges,
        unresolved_imports=unresolved,
    )


def test_summary_counts_graph_facts() -> None:
    summary = build_graph_summary(
        make_graph(), generated_at=datetime(2026, 6, 19, tzinfo=UTC)
    )

    assert summary.counts.directory_nodes == 1
    assert summary.counts.file_nodes == 3
    assert summary.counts.manifest_entry_nodes == 1
    assert summary.counts.contains_edges == 2
    assert summary.counts.import_edges == 3
    assert summary.counts.unresolved_imports == UNRESOLVED_IMPORT_SAMPLE_LIMIT + 2


def test_summary_fan_counts_use_only_import_edges() -> None:
    summary = build_graph_summary(make_graph())

    assert summary.top_fan_in_files[0].path == "b.py"
    assert summary.top_fan_in_files[0].incoming_edges == 2
    assert summary.top_fan_out_files[0].path == "a.py"
    assert summary.top_fan_out_files[0].outgoing_edges == 2


def test_summary_lists_entrypoints_and_bounds_unresolved_sample() -> None:
    summary = build_graph_summary(make_graph())

    assert summary.declared_entrypoints[0].path == "a.py"
    assert (
        summary.declared_entrypoints[0].source == "pyproject.toml:project.scripts.app"
    )
    assert len(summary.unresolved_imports_sample) == UNRESOLVED_IMPORT_SAMPLE_LIMIT


def test_summary_output_is_deterministic() -> None:
    generated_at = datetime(2026, 6, 19, tzinfo=UTC)

    first = build_graph_summary(make_graph(), generated_at=generated_at)
    second = build_graph_summary(make_graph(), generated_at=generated_at)

    assert first == second
