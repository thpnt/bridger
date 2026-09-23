"""Narrow structured boundary to vendored Graphify graph algorithms."""

from __future__ import annotations

import networkx as nx  # type: ignore[import-untyped]

from bridger._vendor.graphify.affected import (
    DEFAULT_AFFECTED_RELATIONS,
    AffectedHit,
)
from bridger._vendor.graphify.affected import (
    affected_nodes as _affected_nodes,
)
from bridger._vendor.graphify.serve import (
    QueryGraphSelection,
    query_graph_selection,
)

_AFFECTED_SAFETY_SENTINEL = 501


def query_graph(
    graph: nx.Graph,
    query: str,
    *,
    depth: int,
) -> QueryGraphSelection:
    """Delegate natural-language graph selection to Graphify."""
    return query_graph_selection(graph, query, depth=depth)


def affected_nodes(
    graph: nx.Graph,
    root_node_id: str,
) -> tuple[AffectedHit, ...]:
    """Delegate full reverse structural traversal to Graphify."""
    return tuple(
        _affected_nodes(
            graph,
            root_node_id,
            relations=DEFAULT_AFFECTED_RELATIONS,
            depth=None,
            max_nodes=_AFFECTED_SAFETY_SENTINEL,
        )
    )


__all__ = [
    "AffectedHit",
    "DEFAULT_AFFECTED_RELATIONS",
    "QueryGraphSelection",
    "affected_nodes",
    "query_graph",
]
