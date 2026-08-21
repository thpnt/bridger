"""Bridger's Layer 3 correctness checks around Graphify outputs."""

from pathlib import Path
from typing import Any, Literal

import networkx as nx  # type: ignore[import-untyped]

from bridger.contracts.files import FileIndex
from bridger.contracts.graph import GraphDiagnostics, RepositoryGraph
from bridger.contracts.repository import RepositoryContext


def validate_graph_intelligence(
    context: RepositoryContext,
    file_index: FileIndex,
    graph: RepositoryGraph,
    graphify_extraction: dict[str, Any],
    derived_state: dict[str, Any],
    build_observations: dict[str, Any],
) -> GraphDiagnostics:
    """Validate Layer 3 invariants and summarize graph construction quality."""
    failures = _repository_identity_failures(context, file_index)
    failures.extend(_graph_identity_failures(context, graph))
    failures.extend(_file_index_path_failures(context, file_index, graph))
    invalid_records = list(build_observations["invalid_records"])
    invalid_records.extend(build_observations["deterministic_violations"])
    if type(graph) is not nx.DiGraph:
        invalid_records.append("graph is not a networkx.DiGraph")
    invalid_records.extend(_graph_record_failures(graph))
    invalid_records.extend(_hyperedge_failures(graph))
    coverage_complete, coverage_failures = _community_coverage(
        graph,
        derived_state.get("communities", {}),
    )
    invalid_records.extend(coverage_failures)
    structural_failures = _structural_analysis_failures(graph, derived_state)
    dropped_records = _dropped_records(build_observations)
    if failures or invalid_records or structural_failures:
        severity: Literal["info", "warning", "error"] = "error"
        publication_blocking = True
    elif dropped_records or build_observations["dangling_endpoints"]:
        severity = "warning"
        publication_blocking = False
    else:
        severity = "info"
        publication_blocking = False
    communities = derived_state.get("communities", {})
    return GraphDiagnostics(
        input_node_count=build_observations["input_node_count"],
        output_node_count=graph.number_of_nodes(),
        input_edge_count=build_observations["input_edge_count"],
        output_edge_count=graph.number_of_edges(),
        input_hyperedge_count=build_observations["input_hyperedge_count"],
        output_hyperedge_count=len(graph.graph.get("hyperedges", [])),
        invalid_records=invalid_records,
        dropped_records=dropped_records,
        dangling_endpoints=build_observations["dangling_endpoints"],
        possible_same_endpoint_edge_collapse_count=build_observations[
            "possible_same_endpoint_edge_collapse_count"
        ],
        isolated_node_count=len(list(nx.isolates(graph))),
        community_count=len(communities),
        single_node_community_count=sum(
            1 for members in communities.values() if len(members) == 1
        ),
        community_coverage_complete=coverage_complete,
        file_index_consistency_failures=failures,
        structural_analysis_reference_failures=structural_failures,
        severity=severity,
        publication_blocking=publication_blocking,
    )


def _repository_identity_failures(
    context: RepositoryContext,
    file_index: FileIndex,
) -> list[str]:
    failures: list[str] = []
    if context.repository_id != file_index.repository_id:
        failures.append("RepositoryContext and FileIndex repository_id differ")
    if context.revision != file_index.revision:
        failures.append("RepositoryContext and FileIndex revision differ")
    if context.scope_path != file_index.scope_path:
        failures.append("RepositoryContext and FileIndex scope_path differ")
    return failures


def _graph_identity_failures(
    context: RepositoryContext,
    graph: RepositoryGraph,
) -> list[str]:
    failures: list[str] = []
    for key, expected_value in (
        ("repository_id", context.repository_id),
        ("revision", context.revision),
        ("scope_path", context.scope_path),
    ):
        if graph.graph.get(key) != expected_value:
            failures.append(f"graph {key} does not match RepositoryContext")
    return failures


def _graph_record_failures(graph: RepositoryGraph) -> list[str]:
    failures: list[str] = []
    for node_id, attributes in graph.nodes(data=True):
        if not isinstance(node_id, str):
            failures.append(f"node has non-string id {node_id!r}")
        source_file = attributes.get("source_file")
        if source_file is not None and not isinstance(source_file, str):
            failures.append(f"node {node_id!r} has invalid source_file")
    for source, target in graph.edges():
        if source not in graph or target not in graph:
            failures.append(f"edge {source!r} -> {target!r} has a missing endpoint")
    return failures


def _file_index_path_failures(
    context: RepositoryContext,
    file_index: FileIndex,
    graph: RepositoryGraph,
) -> list[str]:
    indexed_paths = {record.path for record in file_index.files}
    failures: list[str] = []
    for node_id, attributes in graph.nodes(data=True):
        _append_source_file_failure(
            failures,
            f"node {node_id!r}",
            attributes.get("source_file"),
            context,
            indexed_paths,
        )
    for source, target, attributes in graph.edges(data=True):
        _append_source_file_failure(
            failures,
            f"edge {source!r} -> {target!r}",
            attributes.get("source_file"),
            context,
            indexed_paths,
        )
    for index, hyperedge in enumerate(graph.graph.get("hyperedges", [])):
        if isinstance(hyperedge, dict):
            _append_source_file_failure(
                failures,
                f"hyperedge[{index}]",
                hyperedge.get("source_file"),
                context,
                indexed_paths,
            )
    return failures


def _append_source_file_failure(
    failures: list[str],
    record_name: str,
    source_file: object,
    context: RepositoryContext,
    indexed_paths: set[str],
) -> None:
    if not isinstance(source_file, str) or not source_file:
        return
    if "://" in source_file or source_file.startswith(("external:", "stdlib:")):
        return
    source_path = Path(source_file)
    if source_path.is_absolute():
        try:
            relative_path = source_path.resolve().relative_to(
                context.root_path.resolve()
            )
        except ValueError:
            return
        normalized_path = relative_path.as_posix()
    else:
        normalized_path = source_path.as_posix()
    if normalized_path not in indexed_paths:
        failures.append(
            f"{record_name} claims source_file absent from FileIndex: {normalized_path}"
        )


def _hyperedge_failures(graph: RepositoryGraph) -> list[str]:
    failures: list[str] = []
    hyperedges = graph.graph.get("hyperedges", [])
    if not isinstance(hyperedges, list):
        return ["graph hyperedges metadata is not a list"]
    for index, hyperedge in enumerate(hyperedges):
        if not isinstance(hyperedge, dict):
            failures.append(f"hyperedge[{index}] is not an object")
            continue
        members = hyperedge.get("nodes")
        if not isinstance(members, list):
            failures.append(f"hyperedge[{index}] has no member list")
            continue
        for member in members:
            if member not in graph:
                failures.append(
                    f"hyperedge[{index}] references missing node {member!r}"
                )
    return failures


def _community_coverage(
    graph: RepositoryGraph,
    communities: object,
) -> tuple[bool, list[str]]:
    if not isinstance(communities, dict):
        return False, ["communities are not a dictionary"]
    members = [member for community in communities.values() for member in community]
    member_set = set(members)
    graph_nodes = set(graph.nodes)
    failures: list[str] = []
    if len(members) != len(member_set):
        failures.append("community membership is not unique")
    if member_set != graph_nodes:
        failures.append("communities do not cover exactly the graph nodes")
    return not failures, failures


def _structural_analysis_failures(
    graph: RepositoryGraph,
    derived_state: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    god_nodes = derived_state.get("god_nodes", [])
    if not isinstance(god_nodes, list):
        return ["god_nodes analysis is not a list"]
    for index, node in enumerate(god_nodes):
        if not isinstance(node, dict) or node.get("id") not in graph:
            failures.append(f"god_nodes[{index}] references an unknown node")
    for key in ("surprising_connections", "suggested_questions"):
        if not isinstance(derived_state.get(key), list):
            failures.append(f"{key} analysis is not a list")
    return failures


def _dropped_records(build_observations: dict[str, Any]) -> list[str]:
    dropped: list[str] = []
    for record_type in ("node", "edge", "hyperedge"):
        input_count = build_observations[f"input_{record_type}_count"]
        output_count = build_observations[f"output_{record_type}_count"]
        if output_count < input_count:
            dropped.append(f"{record_type}s: {input_count - output_count}")
    return dropped
