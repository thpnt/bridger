"""Deterministic Markdown presentation for canonical consumption results."""

from __future__ import annotations

from collections.abc import Sequence

from bridger.contracts.consumption import (
    BrainContext,
    GraphEdge,
    GraphNode,
    ImpactGraph,
    ImpactNode,
    ImpactResult,
    UnderstandGraphContext,
    UnderstandResult,
)

_IMPACT_NOTE = "Potential structural impact; not guaranteed semantic breakage."


def render_intelligence_markdown(
    result: UnderstandResult | ImpactResult,
) -> str:
    """Render a canonical UNDERSTAND or IMPACT result as compact Markdown."""
    if isinstance(result, UnderstandResult):
        return _render_understand(result)
    return _render_impact(result)


def _render_understand(result: UnderstandResult) -> str:
    lines = [
        "# UNDERSTAND",
        _state_line(result),
        _completeness_line(result),
    ]
    _append_truncation_note(lines, result)
    _append_warnings(lines, result.warnings)
    lines.extend(["", "## Brain", ""])
    lines.extend(_render_brain_contexts(result.brain_context) or ["No matches."])
    lines.extend(["", "## Graph", ""])
    lines.extend(_render_graph(result.graph_context) or ["No matches."])
    return "\n".join(lines) + "\n"


def _render_impact(result: ImpactResult) -> str:
    lines = ["# IMPACT", _IMPACT_NOTE, _state_line(result)]

    if result.resolution_issues:
        _append_warnings(lines, result.warnings)
        lines.extend(["", "Resolution failed; traversal not executed.", "", "Issues:"])
        for issue in result.resolution_issues:
            lines.append(f"{issue.selector} | {issue.reason}")
            for candidate in issue.candidates:
                name = candidate.qualified_name or candidate.name
                coordinate = _format_coordinate(
                    candidate.path, candidate.start_line, candidate.end_line
                )
                line = f"  {candidate.symbol_id} | {name} | {candidate.kind}"
                if coordinate:
                    line += f" | {coordinate}"
                lines.append(line)
        return "\n".join(lines) + "\n"

    graph = result.affected_graph
    assert graph is not None
    aliases = _node_aliases(graph.nodes)
    lines.append(_completeness_line(result))
    _append_truncation_note(lines, result)
    _append_warnings(lines, result.warnings)
    lines.extend(["", "Roots:"])
    for root in result.resolved_roots:
        root_aliases = " ".join(aliases[node_id] for node_id in root.graph_node_ids)
        lines.append(f"{root.selector} -> {root_aliases}")

    lines.extend(["", "## Affected graph", ""])
    lines.extend(_render_graph(graph, impact=True) or ["No matches."])
    lines.extend(["", "## Brain enrichment", ""])
    lines.extend(
        _render_brain_contexts(result.brain_enrichment) or ["No lexical matches."]
    )
    return "\n".join(lines) + "\n"


def _state_line(result: UnderstandResult | ImpactResult) -> str:
    revision = result.revision
    return (
        f"State: {revision.repository_id}@{revision.repository_revision} "
        f"| graph={revision.graph_snapshot_id} "
        f"| overlay={revision.enrichment_overlay_id}"
    )


def _completeness_line(result: UnderstandResult | ImpactResult) -> str:
    brain = "no" if result.completeness.brain_truncated else "yes"
    graph = "no" if result.completeness.graph_truncated else "yes"
    return f"Complete: brain={brain} | graph={graph}"


def _append_truncation_note(
    lines: list[str], result: UnderstandResult | ImpactResult
) -> None:
    if result.completeness.brain_truncated or result.completeness.graph_truncated:
        lines.append("Note: truncated sections may omit relevant results.")


def _append_warnings(lines: list[str], warnings: list[str]) -> None:
    lines.extend(f"Warning: {warning}" for warning in warnings)


def _render_brain_contexts(contexts: list[BrainContext]) -> list[str]:
    lines: list[str] = []
    for context in contexts:
        parts = [
            f"`{_format_coordinate(context.path, context.start_line, context.end_line)}`"
        ]
        if context.heading:
            parts.append(context.heading)
        if context.semantic_owner:
            parts.append(context.semantic_owner)
        lines.append(" | ".join(parts))
        lines.extend(
            f"> {excerpt_line}" if excerpt_line else ">"
            for excerpt_line in context.excerpt.split("\n")
        )
    return lines


def _render_graph(
    graph: UnderstandGraphContext | ImpactGraph,
    *,
    impact: bool = False,
) -> list[str]:
    if not graph.nodes:
        return []

    aliases = _node_aliases(graph.nodes)
    lines: list[str] = []
    if isinstance(graph, UnderstandGraphContext) and graph.seed_node_ids:
        seeds = " ".join(aliases[node_id] for node_id in graph.seed_node_ids)
        lines.extend([f"Seeds: {seeds}", ""])

    lines.append("Nodes:")
    for node in graph.nodes:
        lines.append(_format_node(node, aliases[node.node_id], impact=impact))

    if graph.edges:
        lines.extend(["", "Edges:"])
        lines.extend(_format_edge(edge, aliases) for edge in graph.edges)

    if isinstance(graph, ImpactGraph) and graph.important_node_ids:
        important = " ".join(aliases[node_id] for node_id in graph.important_node_ids)
        lines.extend(["", f"Important: {important}"])

    if graph.communities:
        communities = " | ".join(
            f"C{community.community_id}={community.label}"
            for community in graph.communities
        )
        lines.extend(["", f"Communities: {communities}"])
    return lines


def _node_aliases(nodes: Sequence[GraphNode]) -> dict[str, str]:
    return {node.node_id: f"N{index}" for index, node in enumerate(nodes, start=1)}


def _format_node(node: GraphNode, alias: str, *, impact: bool = False) -> str:
    depth = f" [d{node.depth}]" if impact and isinstance(node, ImpactNode) else ""
    line = f"{alias}{depth} {node.label}"
    coordinate = _format_coordinate(
        node.source_path, node.source_start_line, node.source_end_line
    )
    if coordinate:
        line += f" | {coordinate}"
    if node.node_id != node.label:
        line += f" | id={node.node_id}"
    if node.symbol_ids:
        line += f" | sym={','.join(node.symbol_ids)}"
    if node.community_id is not None:
        line += f" | C{node.community_id}"
    return line


def _format_edge(edge: GraphEdge, aliases: dict[str, str]) -> str:
    line = (
        f"{aliases[edge.source_node_id]} -{edge.relation}-> "
        f"{aliases[edge.target_node_id]}"
    )
    coordinate = _format_coordinate(
        edge.evidence_path, edge.evidence_start_line, edge.evidence_end_line
    )
    if coordinate:
        line += f" @ {coordinate}"
    if edge.evidence:
        line += f" | {edge.evidence}"
    return line


def _format_coordinate(
    path: str | None,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str | None:
    if path is None:
        return None
    if start_line is None:
        return path
    if end_line == start_line:
        return f"{path}:L{start_line}"
    return f"{path}:L{start_line}-L{end_line}"


__all__ = ["render_intelligence_markdown"]
