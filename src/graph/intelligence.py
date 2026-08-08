"""Direct Layer 3 orchestration over Graphify's deterministic engine."""

from collections import Counter
from typing import Any

import networkx as nx  # type: ignore[import-untyped]

from graph.validation import validate_graph_intelligence
from graphify.analyze import god_nodes, suggest_questions, surprising_connections
from graphify.build import build_from_json
from graphify.cluster import (
    cluster,
    community_member_sigs,
    label_communities_by_hub,
    score_all,
)
from models.files import FileIndex
from models.graph import GraphConstructionConfig, GraphDiagnostics, RepositoryGraph
from models.repository import RepositoryContext


def build_graph_intelligence(
    context: RepositoryContext,
    file_index: FileIndex,
    graphify_extraction: dict[str, Any],
    config: GraphConstructionConfig,
) -> tuple[RepositoryGraph, GraphDiagnostics, dict[str, Any]]:
    """Build and validate deterministic intelligence for one repository revision."""
    graph, build_observations = construct_repository_graph(
        context,
        graphify_extraction,
    )
    community_structure = compute_community_structure(graph, config)
    structural_analysis = analyze_graph_structure(
        graph,
        community_structure,
        config,
    )
    derived_state = {**community_structure, **structural_analysis}
    diagnostics = validate_graph_intelligence(
        context,
        file_index,
        graph,
        graphify_extraction,
        derived_state,
        build_observations,
    )
    return graph, diagnostics, derived_state


def construct_repository_graph(
    context: RepositoryContext,
    graphify_extraction: dict[str, Any],
) -> tuple[RepositoryGraph, dict[str, Any]]:
    """Use Graphify's builder with Bridger's fixed directed graph policy."""
    observations = _build_observations(graphify_extraction)
    graph = build_from_json(
        graphify_extraction,
        directed=True,
        root=context.root_path,
    )
    if type(graph) is not nx.DiGraph:
        raise TypeError("Graphify did not construct the required networkx.DiGraph")
    graph.graph["repository_id"] = context.repository_id
    graph.graph["revision"] = context.revision
    graph.graph["scope_path"] = context.scope_path
    observations["output_node_count"] = graph.number_of_nodes()
    observations["output_edge_count"] = graph.number_of_edges()
    observations["output_hyperedge_count"] = len(graph.graph.get("hyperedges", []))
    return graph, observations


def compute_community_structure(
    graph: RepositoryGraph,
    config: GraphConstructionConfig,
) -> dict[str, Any]:
    """Compute Graphify's Leiden communities and deterministic derived labels."""
    communities = cluster(
        graph,
        resolution=config.community_resolution,
        exclude_hubs_percentile=config.hub_exclusion_percentile,
    )
    return {
        "communities": communities,
        "cohesion": score_all(graph, communities),
        "community_member_signatures": community_member_sigs(communities),
        "community_labels": label_communities_by_hub(graph, communities),
    }


def analyze_graph_structure(
    graph: RepositoryGraph,
    community_structure: dict[str, Any],
    config: GraphConstructionConfig,
) -> dict[str, Any]:
    """Compute Graphify's deterministic structural analysis outputs."""
    communities = community_structure["communities"]
    community_labels = community_structure["community_labels"]
    return {
        "god_nodes": god_nodes(graph, top_n=config.god_node_limit),
        "surprising_connections": surprising_connections(
            graph,
            communities,
            top_n=config.surprising_connections_limit,
        ),
        "suggested_questions": suggest_questions(
            graph,
            communities,
            community_labels,
            top_n=config.suggested_questions_limit,
        ),
    }


def _build_observations(graphify_extraction: dict[str, Any]) -> dict[str, Any]:
    nodes = graphify_extraction.get("nodes", [])
    edges = graphify_extraction.get("edges", graphify_extraction.get("links", []))
    hyperedges = graphify_extraction.get("hyperedges", [])
    node_records = nodes if isinstance(nodes, list) else []
    edge_records = edges if isinstance(edges, list) else []
    hyperedge_records = hyperedges if isinstance(hyperedges, list) else []
    node_ids = {
        record.get("id")
        for record in node_records
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }
    endpoint_pairs: Counter[tuple[str, str]] = Counter()
    dangling_endpoints: list[str] = []
    invalid_records: list[str] = []
    for index, edge in enumerate(edge_records):
        if not isinstance(edge, dict):
            invalid_records.append(f"edge[{index}] is not an object")
            continue
        source = edge.get("source", edge.get("from"))
        target = edge.get("target", edge.get("to"))
        if not isinstance(source, str) or not isinstance(target, str):
            invalid_records.append(f"edge[{index}] has invalid endpoints")
            continue
        if source not in node_ids or target not in node_ids:
            dangling_endpoints.append(f"{source} -> {target}")
            continue
        endpoint_pairs[(source, target)] += 1
    for index, node in enumerate(node_records):
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            invalid_records.append(f"node[{index}] has no string id")
    for index, hyperedge in enumerate(hyperedge_records):
        if not isinstance(hyperedge, dict):
            invalid_records.append(f"hyperedge[{index}] is not an object")
    deterministic_violations = _deterministic_violations(
        node_records,
        edge_records,
        hyperedge_records,
    )
    return {
        "input_node_count": len(node_records),
        "input_edge_count": len(edge_records),
        "input_hyperedge_count": len(hyperedge_records),
        "invalid_records": invalid_records,
        "dangling_endpoints": sorted(set(dangling_endpoints)),
        "possible_same_endpoint_edge_collapse_count": sum(
            count - 1 for count in endpoint_pairs.values() if count > 1
        ),
        "deterministic_violations": deterministic_violations,
    }


def _deterministic_violations(
    nodes: list[Any],
    edges: list[Any],
    hyperedges: list[Any],
) -> list[str]:
    violations: list[str] = []
    for record_type, records in (
        ("node", nodes),
        ("edge", edges),
        ("hyperedge", hyperedges),
    ):
        for index, record in enumerate(records):
            if isinstance(record, dict) and record.get("_origin") not in (
                None,
                "ast",
            ):
                violations.append(
                    f"{record_type}[{index}] has non-deterministic origin "
                    f"{record.get('_origin')!r}"
                )
    return violations
