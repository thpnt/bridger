"""Deterministic composition over Brain and repository navigation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from bridger.contracts.consumption import (
    Authority,
    BridgerRef,
    BridgerRefKind,
    Completeness,
    IntelligenceItem,
    IntelligenceQueryRequest,
    IntelligenceReadRequest,
    IntelligenceResult,
    Lens,
    Provenance,
    ResultOperation,
    ScopeKind,
    ScopeRef,
    Substrate,
)
from bridger.contracts.enrichment import EnrichmentTargetReference, EnrichmentTargetType
from bridger.contracts.files import SourceReadResult
from bridger.contracts.navigation import CompositeEntityView, FileOverview
from bridger.navigation.brain import BrainNavigator
from bridger.navigation.navigator import RepositoryNavigator

DEFAULT_BRIDGER_RESULT_LIMIT = 10
MAX_BRIDGER_RESULT_LIMIT = 20

_GRAPH_REF_TYPES: dict[BridgerRefKind, EnrichmentTargetType] = {
    BridgerRefKind.NODE: "node",
    BridgerRefKind.EDGE: "edge",
    BridgerRefKind.HYPEREDGE: "hyperedge",
    BridgerRefKind.COMMUNITY: "community",
    BridgerRefKind.GRAPH: "graph",
}
_GRAPH_ITEM_KINDS: dict[EnrichmentTargetType, BridgerRefKind] = {
    "node": BridgerRefKind.NODE,
    "edge": BridgerRefKind.EDGE,
    "hyperedge": BridgerRefKind.HYPEREDGE,
    "community": BridgerRefKind.COMMUNITY,
    "graph": BridgerRefKind.GRAPH,
}


@dataclass(frozen=True)
class _RepositoryContribution:
    items: list[IntelligenceItem]
    truncated: bool = False
    more_available: bool = False


class BridgerNavigator:
    """Route one consumption request across the immutable V0 navigators."""

    def __init__(
        self,
        brain: BrainNavigator,
        repository: RepositoryNavigator,
    ) -> None:
        self._brain = brain
        self._repository = repository
        self._repository_revision = repository.source_identity[1]
        if brain.repository_revision != self._repository_revision:
            raise ValueError("Brain and repository navigators use different revisions")

    def query(self, request: IntelligenceQueryRequest) -> IntelligenceResult:
        """Run the deterministic recipe selected by lens and explicit scope."""
        final_limit = _result_limit(request.limit)

        if request.lens is Lens.GUARDRAILS:
            return self._brain_only(request, final_limit)

        if request.lens is Lens.UNDERSTAND:
            if request.scope is None or request.scope.kind is ScopeKind.BRAIN_REF:
                return self._brain_only(request, final_limit)

            brain = self._search_brain(request, final_limit)
            repository = self._understand_repository(request.scope)
            return self._compose(request, brain, repository, primary="brain")

        if request.lens is Lens.IMPACT:
            brain = self._search_brain(request, final_limit)
            repository = self._impact_repository(request.scope)
            return self._compose(request, brain, repository, primary="repository")

        raise ValueError(f"unsupported intelligence lens: {request.lens}")

    def read(self, request: IntelligenceReadRequest) -> IntelligenceResult:
        """Resolve one already-addressed object without performing semantic search."""
        ref = request.ref
        self._require_revision(ref)

        if ref.kind in {
            BridgerRefKind.BRAIN_DOCUMENT,
            BridgerRefKind.BRAIN_CONTEXT,
        }:
            return self._brain.read(request)
        if ref.kind in {BridgerRefKind.BRAIN_CLAIM, BridgerRefKind.EVIDENCE}:
            raise NotImplementedError(
                f"{ref.kind.value.upper()} is not supported in V0"
            )
        if request.expand is not None:
            raise ValueError("repository READ expansions are not supported in V0")

        if ref.kind in _GRAPH_REF_TYPES:
            view = self._repository.get_graph_entity(
                _GRAPH_REF_TYPES[ref.kind], ref.target_ref
            )
            contribution = _RepositoryContribution(
                items=[self._graph_item(view)],
                truncated=_view_truncated(view),
                more_available=_view_truncated(view),
            )
        elif ref.kind is BridgerRefKind.FILE:
            if not isinstance(ref.target_ref, str):
                raise ValueError("FILE ref requires a canonical path")
            overview = self._repository.get_file_overview(ref.target_ref)
            contribution = _RepositoryContribution(
                items=[self._file_item(overview)],
                truncated=_file_truncated(overview),
                more_available=_file_truncated(overview),
            )
        elif ref.kind is BridgerRefKind.SYMBOL:
            if not isinstance(ref.target_ref, str):
                raise ValueError("SYMBOL ref requires a canonical symbol_id")
            excerpt = self._repository.read_symbol_excerpt(ref.target_ref)
            nodes = self._repository.symbol_to_graph(ref.target_ref)
            contribution = _RepositoryContribution(
                items=[self._symbol_item(ref.target_ref, excerpt, nodes)],
                truncated=excerpt.truncated,
                more_available=excerpt.truncated,
            )
        else:
            raise ValueError(f"unsupported Bridger ref kind: {ref.kind.value}")

        return self._repository_read_result(contribution)

    def _brain_only(
        self,
        request: IntelligenceQueryRequest,
        final_limit: int,
    ) -> IntelligenceResult:
        result = self._search_brain(request, final_limit)
        return IntelligenceResult(
            operation=ResultOperation.QUERY,
            repository_revision=self._repository_revision,
            lens=request.lens,
            query=request.query,
            scope=request.scope,
            items=result.items[:final_limit],
            completeness=Completeness(
                returned_count=len(result.items[:final_limit]),
                truncated=result.completeness.truncated,
                more_available=result.completeness.more_available,
            ),
        )

    def _search_brain(
        self,
        request: IntelligenceQueryRequest,
        final_limit: int,
    ) -> IntelligenceResult:
        return self._brain.search(request.model_copy(update={"limit": final_limit}))

    def _understand_repository(self, scope: ScopeRef) -> _RepositoryContribution:
        if scope.kind is ScopeKind.REPOSITORY:
            graph_overview = self._repository.get_graph_entity("graph", "graph")
            communities = self._repository.list_graph_communities(
                limit=MAX_BRIDGER_RESULT_LIMIT
            )
            central_nodes = self._repository.get_graph_central_nodes(
                limit=MAX_BRIDGER_RESULT_LIMIT
            )
            views = [graph_overview, *communities, *central_nodes]
            incomplete = any(_view_truncated(view) for view in views)
            return _RepositoryContribution(
                items=[self._graph_item(view) for view in views],
                truncated=incomplete,
                more_available=incomplete,
            )

        if scope.kind is ScopeKind.PATH:
            if not isinstance(scope.value, str):
                raise ValueError("path scope requires a canonical path")
            file_overview = self._repository.get_file_overview(scope.value)
            incomplete = _file_truncated(file_overview)
            return _RepositoryContribution(
                items=[self._file_item(file_overview)],
                truncated=incomplete,
                more_available=incomplete,
            )

        if scope.kind is ScopeKind.SYMBOL:
            if not isinstance(scope.value, str):
                raise ValueError("symbol scope requires a canonical symbol_id")
            excerpt = self._repository.read_symbol_excerpt(scope.value)
            nodes = self._repository.symbol_to_graph(scope.value)
            return _RepositoryContribution(
                items=[self._symbol_item(scope.value, excerpt, nodes)],
                truncated=excerpt.truncated,
                more_available=excerpt.truncated,
            )

        if scope.kind is ScopeKind.GRAPH_ENTITY:
            ref = self._graph_scope_ref(scope)
            view = self._repository.get_graph_entity(
                _GRAPH_REF_TYPES[ref.kind], ref.target_ref
            )
            incomplete = _view_truncated(view)
            return _RepositoryContribution(
                items=[self._graph_item(view)],
                truncated=incomplete,
                more_available=incomplete,
            )

        raise ValueError(f"unsupported repository scope: {scope.kind.value}")

    def _impact_repository(self, scope: ScopeRef | None) -> _RepositoryContribution:
        if scope is None:
            raise ValueError("IMPACT requires a concrete scope")
        seeds, seed_incomplete = self._impact_seeds(scope)
        items: list[IntelligenceItem] = []
        seen: set[str] = set()
        truncated = seed_incomplete
        for seed in seeds:
            traversal = self._repository.get_graph_subgraph(
                seed,
                direction="incoming",
                depth=2,
            )
            truncated = truncated or traversal.truncated
            for view in traversal.nodes:
                identity = _target_identity(view.target_ref)
                if identity in seen:
                    continue
                seen.add(identity)
                items.append(self._graph_item(view))
        return _RepositoryContribution(
            items=items,
            truncated=truncated,
            more_available=truncated,
        )

    def _impact_seeds(self, scope: ScopeRef) -> tuple[list[str], bool]:
        if scope.kind is ScopeKind.PATH:
            if not isinstance(scope.value, str):
                raise ValueError("PATH impact scope requires a canonical path")
            seeds = self._repository.file_to_graph(scope.value)
            if not seeds:
                raise ValueError("PATH impact scope has no graph association")
            return _ordered_seeds(seeds), False

        if scope.kind is ScopeKind.SYMBOL:
            if not isinstance(scope.value, str):
                raise ValueError("SYMBOL impact scope requires a canonical symbol_id")
            seeds = self._repository.symbol_to_graph(scope.value)
            if not seeds:
                raise ValueError("SYMBOL impact scope has no graph association")
            return _ordered_seeds(seeds), False

        if scope.kind is not ScopeKind.GRAPH_ENTITY:
            raise ValueError("IMPACT scope must be path, symbol, or graph_entity")
        ref = self._graph_scope_ref(scope)
        if ref.kind is BridgerRefKind.GRAPH:
            raise ValueError("GRAPH-wide IMPACT is too broad for V0")
        if ref.kind is BridgerRefKind.NODE:
            if not isinstance(ref.target_ref, str):
                raise ValueError("NODE impact scope requires a node_id")
            return [ref.target_ref], False
        if ref.kind is BridgerRefKind.EDGE:
            view = self._repository.get_graph_entity("edge", ref.target_ref)
            source = view.deterministic.get("source_node_id")
            target = view.deterministic.get("target_node_id")
            return _required_node_seeds([source, target], "EDGE"), False

        view = self._repository.get_graph_entity(
            _GRAPH_REF_TYPES[ref.kind], ref.target_ref
        )
        member_key = "nodes" if ref.kind is BridgerRefKind.HYPEREDGE else "members"
        members = view.deterministic.get(member_key)
        if not isinstance(members, list):
            raise ValueError(f"{ref.kind.value.upper()} impact scope has no members")
        return (
            _required_node_seeds(members, ref.kind.value.upper()),
            _view_truncated(view),
        )

    def _compose(
        self,
        request: IntelligenceQueryRequest,
        brain: IntelligenceResult,
        repository: _RepositoryContribution,
        *,
        primary: str,
    ) -> IntelligenceResult:
        final_limit = _result_limit(request.limit)
        supporting_limit = 0 if final_limit == 1 else max(1, final_limit // 3)
        primary_limit = final_limit - supporting_limit

        primary_items, supporting_items = (
            (brain.items, repository.items)
            if primary == "brain"
            else (repository.items, brain.items)
        )
        primary_count = min(len(primary_items), primary_limit)
        supporting_count = min(len(supporting_items), supporting_limit)
        remaining = final_limit - primary_count - supporting_count
        if primary_count < primary_limit:
            supporting_count += min(remaining, len(supporting_items) - supporting_count)
        elif supporting_count < supporting_limit:
            primary_count += min(remaining, len(primary_items) - primary_count)

        selected_primary = primary_items[:primary_count]
        selected_supporting = supporting_items[:supporting_count]
        items = [*selected_primary, *selected_supporting]
        composition_truncated = primary_count < len(
            primary_items
        ) or supporting_count < len(supporting_items)
        truncated = (
            brain.completeness.truncated
            or repository.truncated
            or composition_truncated
        )
        more_available = (
            brain.completeness.more_available
            or repository.more_available
            or composition_truncated
        )
        return IntelligenceResult(
            operation=ResultOperation.QUERY,
            repository_revision=self._repository_revision,
            lens=request.lens,
            query=request.query,
            scope=request.scope,
            items=items,
            completeness=Completeness(
                returned_count=len(items),
                truncated=truncated,
                more_available=more_available,
            ),
        )

    def _repository_read_result(
        self, contribution: _RepositoryContribution
    ) -> IntelligenceResult:
        return IntelligenceResult(
            operation=ResultOperation.READ,
            repository_revision=self._repository_revision,
            items=contribution.items,
            completeness=Completeness(
                returned_count=len(contribution.items),
                truncated=contribution.truncated,
                more_available=contribution.more_available,
            ),
        )

    def _graph_scope_ref(self, scope: ScopeRef) -> BridgerRef:
        if (
            not isinstance(scope.value, BridgerRef)
            or scope.value.kind not in _GRAPH_REF_TYPES
        ):
            raise ValueError(
                "BridgerNavigator graph scopes require a revision-bound graph ref"
            )
        self._require_revision(scope.value)
        return scope.value

    def _graph_item(self, view: CompositeEntityView) -> IntelligenceItem:
        kind = _GRAPH_ITEM_KINDS[view.target_type]
        return IntelligenceItem(
            ref=BridgerRef(
                kind=kind,
                target_ref=view.target_ref,
                repository_revision=self._repository_revision,
            ),
            kind=kind,
            title=_view_title(view),
            data=view.model_dump(mode="json"),
            provenance=self._graph_provenance(),
        )

    def _file_item(self, overview: FileOverview) -> IntelligenceItem:
        path = overview.file.path
        related_refs = [
            BridgerRef(
                kind=BridgerRefKind.SYMBOL,
                target_ref=symbol_id,
                repository_revision=self._repository_revision,
            )
            for symbol_id in overview.symbol_ids
        ]
        related_refs.extend(
            BridgerRef(
                kind=BridgerRefKind.NODE,
                target_ref=node_id,
                repository_revision=self._repository_revision,
            )
            for node_id in overview.graph_node_ids
        )
        return IntelligenceItem(
            ref=BridgerRef(
                kind=BridgerRefKind.FILE,
                target_ref=path,
                repository_revision=self._repository_revision,
            ),
            kind=BridgerRefKind.FILE,
            title=path,
            data=overview.model_dump(mode="json"),
            related_refs=related_refs,
            provenance=self._source_provenance(),
        )

    def _symbol_item(
        self,
        symbol_id: str,
        excerpt: SourceReadResult,
        node_ids: list[str],
    ) -> IntelligenceItem:
        return IntelligenceItem(
            ref=BridgerRef(
                kind=BridgerRefKind.SYMBOL,
                target_ref=symbol_id,
                repository_revision=self._repository_revision,
            ),
            kind=BridgerRefKind.SYMBOL,
            title=symbol_id,
            content=excerpt.content,
            data={
                "path": excerpt.path,
                "revision": excerpt.revision,
                "start_line": excerpt.start_line,
                "end_line": excerpt.end_line,
                "content_digest": excerpt.content_digest,
                "encoding": excerpt.encoding,
                "truncated": excerpt.truncated,
            },
            related_refs=[
                BridgerRef(
                    kind=BridgerRefKind.NODE,
                    target_ref=node_id,
                    repository_revision=self._repository_revision,
                )
                for node_id in node_ids
            ],
            provenance=self._source_provenance(),
        )

    def _graph_provenance(self) -> Provenance:
        return Provenance(
            repository_revision=self._repository_revision,
            substrate=Substrate.DETERMINISTIC_GRAPH,
            authority=Authority.DETERMINISTIC,
        )

    def _source_provenance(self) -> Provenance:
        return Provenance(
            repository_revision=self._repository_revision,
            substrate=Substrate.SOURCE,
            authority=Authority.DETERMINISTIC,
        )

    def _require_revision(self, ref: BridgerRef) -> None:
        if ref.repository_revision != self._repository_revision:
            raise ValueError("Bridger ref belongs to a different repository revision")


def _result_limit(value: int | None) -> int:
    limit = value or DEFAULT_BRIDGER_RESULT_LIMIT
    if limit > MAX_BRIDGER_RESULT_LIMIT:
        raise ValueError(
            f"Bridger result limit must be at most {MAX_BRIDGER_RESULT_LIMIT}"
        )
    return limit


def _ordered_seeds(values: list[str]) -> list[str]:
    return sorted(set(values))


def _required_node_seeds(values: object, label: str) -> list[str]:
    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        raise ValueError(f"{label} impact scope has invalid node members")
    seeds = _ordered_seeds(cast(list[str], values))
    if not seeds:
        raise ValueError(f"{label} impact scope has no graph members")
    return seeds


def _view_truncated(view: CompositeEntityView) -> bool:
    return any(
        key.endswith("_truncated") and value is True
        for key, value in view.deterministic.items()
    )


def _file_truncated(overview: FileOverview) -> bool:
    return overview.symbols_truncated or overview.graph_nodes_truncated


def _target_identity(target: EnrichmentTargetReference) -> str:
    return json.dumps(target, sort_keys=True, separators=(",", ":"))


def _view_title(view: CompositeEntityView) -> str:
    for record in view.enrichment:
        if isinstance(record.value, str) and record.value:
            return record.value
    label = view.deterministic.get("deterministic_label")
    if isinstance(label, str) and label:
        return label
    attributes = view.deterministic.get("attributes")
    if isinstance(attributes, dict):
        node_label = attributes.get("label")
        if isinstance(node_label, str) and node_label:
            return node_label
    if isinstance(view.target_ref, str):
        return view.target_ref
    return _target_identity(view.target_ref)


__all__ = [
    "BridgerNavigator",
    "DEFAULT_BRIDGER_RESULT_LIMIT",
    "MAX_BRIDGER_RESULT_LIMIT",
]
