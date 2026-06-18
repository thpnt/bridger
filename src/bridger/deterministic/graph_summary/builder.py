from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from bridger.models.graph_summary import (
    DeclaredEntrypointSummary,
    FanInFile,
    FanOutFile,
    GraphSummaryArtifact,
    GraphSummaryCounts,
    UnresolvedImportSample,
)
from bridger.models.repo_graph import (
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    RepoGraphArtifact,
)

TOP_FILE_LIMIT = 10
UNRESOLVED_IMPORT_SAMPLE_LIMIT = 20


def build_graph_summary(
    graph: RepoGraphArtifact,
    *,
    generated_at: datetime | None = None,
) -> GraphSummaryArtifact:
    nodes_by_id = {node.id: node for node in graph.nodes}
    node_counts = Counter(node.kind for node in graph.nodes)
    edge_counts = Counter(edge.kind for edge in graph.edges)
    incoming: Counter[str] = Counter()
    outgoing: Counter[str] = Counter()
    entrypoints: list[DeclaredEntrypointSummary] = []

    for edge in graph.edges:
        if edge.kind is GraphEdgeKind.IMPORTS:
            outgoing[edge.from_id] += 1
            incoming[edge.to_id] += 1
        elif edge.kind is GraphEdgeKind.DECLARES_ENTRYPOINT:
            entrypoint = _entrypoint_summary(edge.from_id, edge.to_id, nodes_by_id)
            if entrypoint is not None:
                entrypoints.append(entrypoint)

    return GraphSummaryArtifact(
        generated_at=generated_at or datetime.now(UTC),
        counts=GraphSummaryCounts(
            directory_nodes=node_counts[GraphNodeKind.DIRECTORY],
            file_nodes=node_counts[GraphNodeKind.FILE],
            symbol_nodes=node_counts[GraphNodeKind.SYMBOL],
            manifest_entry_nodes=node_counts[GraphNodeKind.MANIFEST_ENTRY],
            framework_pattern_nodes=node_counts[GraphNodeKind.FRAMEWORK_PATTERN],
            contains_edges=edge_counts[GraphEdgeKind.CONTAINS],
            declares_symbol_edges=edge_counts[GraphEdgeKind.DECLARES_SYMBOL],
            import_edges=edge_counts[GraphEdgeKind.IMPORTS],
            declares_entrypoint_edges=edge_counts[GraphEdgeKind.DECLARES_ENTRYPOINT],
            matches_path_pattern_edges=edge_counts[GraphEdgeKind.MATCHES_PATH_PATTERN],
            unresolved_imports=len(graph.unresolved_imports),
        ),
        top_fan_in_files=_fan_in_files(incoming, nodes_by_id),
        top_fan_out_files=_fan_out_files(outgoing, nodes_by_id),
        declared_entrypoints=entrypoints,
        unresolved_imports_sample=[
            UnresolvedImportSample(
                from_path=item.from_path,
                import_text=item.import_text,
                reason=item.reason,
            )
            for item in graph.unresolved_imports[:UNRESOLVED_IMPORT_SAMPLE_LIMIT]
        ],
    )


def build_graph_summary_for_project(
    repo_root: Path,
    *,
    generated_at: datetime | None = None,
) -> GraphSummaryArtifact:
    graph_path = repo_root.resolve() / ".bridger" / "artifacts" / "repo-graph.json"
    graph = RepoGraphArtifact.model_validate_json(graph_path.read_bytes())
    return build_graph_summary(graph, generated_at=generated_at)


def _fan_in_files(
    counts: Counter[str], nodes_by_id: dict[str, GraphNode]
) -> list[FanInFile]:
    files = [
        FanInFile(path=node.path, incoming_edges=count)
        for node_id, count in counts.items()
        if (node := nodes_by_id.get(node_id)) is not None
        and node.kind is GraphNodeKind.FILE
        and node.path is not None
    ]
    files.sort(key=lambda item: (-item.incoming_edges, item.path))
    return files[:TOP_FILE_LIMIT]


def _fan_out_files(
    counts: Counter[str], nodes_by_id: dict[str, GraphNode]
) -> list[FanOutFile]:
    files = [
        FanOutFile(path=node.path, outgoing_edges=count)
        for node_id, count in counts.items()
        if (node := nodes_by_id.get(node_id)) is not None
        and node.kind is GraphNodeKind.FILE
        and node.path is not None
    ]
    files.sort(key=lambda item: (-item.outgoing_edges, item.path))
    return files[:TOP_FILE_LIMIT]


def _entrypoint_summary(
    manifest_id: str,
    file_id: str,
    nodes_by_id: dict[str, GraphNode],
) -> DeclaredEntrypointSummary | None:
    manifest = nodes_by_id.get(manifest_id)
    file_node = nodes_by_id.get(file_id)
    if (
        manifest is None
        or manifest.kind is not GraphNodeKind.MANIFEST_ENTRY
        or manifest.path is None
        or manifest.key is None
        or file_node is None
        or file_node.kind is not GraphNodeKind.FILE
        or file_node.path is None
    ):
        return None
    return DeclaredEntrypointSummary(
        path=file_node.path,
        source=f"{manifest.path}:{manifest.key}",
    )
