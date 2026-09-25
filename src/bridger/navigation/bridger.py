"""Composition of already-computed Brain and repository results."""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType

from bridger.contracts.consumption import (
    Completeness,
    ConsumptionRevision,
    ImpactResult,
    UnderstandResult,
)
from bridger.navigation.brain import BrainNavigator
from bridger.navigation.navigator import RepositoryImpactResult, RepositoryNavigator

MAX_IMPACT_BRAIN_IDENTIFIERS = 100
_IDENTIFIER_TRUNCATION_WARNING = "Brain enrichment identifiers were truncated."


class BridgerNavigator:
    """Compose independent retrieval results under one immutable revision."""

    def __init__(
        self,
        brain: BrainNavigator,
        repository: RepositoryNavigator,
    ) -> None:
        if brain.source_identity != repository.source_identity:
            raise ValueError("Brain and repository authorities do not match")

        repository_id, repository_revision, graph_snapshot_id, overlay_id = (
            repository.source_identity
        )
        if overlay_id is None:
            raise ValueError("Bridger requires a pinned enrichment overlay")

        self._brain = brain
        self._repository = repository
        self._revision = ConsumptionRevision(
            repository_id=repository_id,
            repository_revision=repository_revision,
            graph_snapshot_id=graph_snapshot_id,
            enrichment_overlay_id=overlay_id,
        )
        self._closed = False

    def understand(self, query: str) -> UnderstandResult:
        self._require_open()
        query = _require_query(query)

        brain = self._brain.search_hybrid(query)
        graph = self._repository.query_graph(query)
        return UnderstandResult(
            query=query,
            revision=self._revision,
            brain_context=list(brain.contexts),
            graph_context=graph.context,
            completeness=Completeness(
                brain_truncated=brain.truncated,
                graph_truncated=graph.truncated,
            ),
            warnings=list(brain.warnings),
        )

    def impact(self, symbols: Sequence[str]) -> ImpactResult:
        self._require_open()
        requested = _require_symbols(symbols)
        graph = self._repository.impact(requested)
        if graph.resolution_issues:
            return ImpactResult(
                revision=self._revision,
                requested_symbols=requested,
                resolved_roots=list(graph.resolved_roots),
                resolution_issues=list(graph.resolution_issues),
                affected_graph=None,
                brain_enrichment=[],
                completeness=Completeness(),
                warnings=[],
            )

        identifiers, identifiers_truncated = _impact_brain_identifiers(graph)
        brain = self._brain.search_lexical(identifiers)
        warnings = list(brain.warnings)
        if identifiers_truncated:
            warnings.append(_IDENTIFIER_TRUNCATION_WARNING)

        return ImpactResult(
            revision=self._revision,
            requested_symbols=requested,
            resolved_roots=list(graph.resolved_roots),
            resolution_issues=[],
            affected_graph=graph.affected_graph,
            brain_enrichment=list(brain.contexts),
            completeness=Completeness(
                graph_truncated=graph.truncated,
                brain_truncated=identifiers_truncated or brain.truncated,
            ),
            warnings=warnings,
        )

    @property
    def repository_navigator(self) -> RepositoryNavigator:
        """Return the repository authority already owned by this navigator."""
        self._require_open()
        return self._repository

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._brain.close()

    def __enter__(self) -> BridgerNavigator:
        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("BridgerNavigator is closed")


def _require_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        raise ValueError("query must be non-empty")
    return normalized


def _require_symbols(symbols: Sequence[str]) -> list[str]:
    if isinstance(symbols, (str, bytes, bytearray)):
        raise ValueError("symbols must be a non-empty sequence of selectors")
    if not all(isinstance(symbol, str) for symbol in symbols):
        raise ValueError("symbols must contain only text selectors")
    normalized = list(dict.fromkeys(symbol.strip() for symbol in symbols))
    normalized = [symbol for symbol in normalized if symbol]
    if not normalized:
        raise ValueError("symbols must contain at least one non-empty selector")
    return normalized


def _impact_brain_identifiers(
    impact: RepositoryImpactResult,
) -> tuple[list[str], bool]:
    graph = impact.affected_graph
    if graph is None:
        return [], False

    nodes_by_id = {node.node_id: node for node in graph.nodes}
    prioritized: list[str] = []

    for root in impact.resolved_roots:
        if root.symbol is not None:
            if root.symbol.qualified_name:
                prioritized.append(root.symbol.qualified_name)
            prioritized.append(root.symbol.name)
            prioritized.append(root.symbol.path)
        for node_id in root.graph_node_ids:
            node = nodes_by_id.get(node_id)
            if node is not None:
                prioritized.extend((node.label, node.source_path or ""))

    for node_id in graph.important_node_ids:
        node = nodes_by_id.get(node_id)
        if node is not None:
            prioritized.extend((node.label, node.source_path or ""))

    for node in sorted(graph.nodes, key=lambda item: (item.depth, item.node_id)):
        prioritized.extend((node.label, node.source_path or ""))

    prioritized.extend(community.label for community in graph.communities)
    for node in graph.nodes:
        prioritized.append(node.node_id)
        prioritized.extend(node.symbol_ids)

    identifiers = list(
        dict.fromkeys(value.strip() for value in prioritized if value.strip())
    )
    return identifiers[:MAX_IMPACT_BRAIN_IDENTIFIERS], len(
        identifiers
    ) > MAX_IMPACT_BRAIN_IDENTIFIERS


__all__ = ["BridgerNavigator", "MAX_IMPACT_BRAIN_IDENTIFIERS"]
