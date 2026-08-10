"""Layer 6 composite graph access and repository navigation."""

import json
import re
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from typing import Any, cast

from pydantic import JsonValue
from rapidfuzz.fuzz import WRatio

from graph.lifecycle import (
    load_graph_snapshot_structural_state,
    validate_graph_snapshot,
)
from models.enrichment import (
    EnrichmentRecord,
    EnrichmentTargetReference,
    EnrichmentTargetType,
    GraphEnrichmentOverlay,
)
from models.files import FileIndex, FileRecord, SourceReadRequest, SourceReadResult
from models.graph import GraphBuildResult
from models.navigation import (
    CompositeEntityView,
    FileOverview,
    GraphCommunityView,
    GraphDirection,
    GraphTraversalView,
    RepositorySearchHit,
    RepositorySearchKind,
    SourceContentMatch,
)
from models.repository import RepositoryContext
from models.symbols import SymbolIndex, SymbolKind, SymbolRecord
from repository.errors import RepositoryError
from repository.reader import read_file

DEFAULT_RESULT_LIMIT = 20
DEFAULT_LIST_LIMIT = 100
DEFAULT_MAX_NODES = 50
DEFAULT_MAX_EDGES = 100
DEFAULT_MAX_HYPEREDGES = 25
MAX_RESULT_LIMIT = 100
MAX_LIST_LIMIT = 500
MAX_GRAPH_NODES = 500
MAX_GRAPH_EDGES = 1_000
MAX_GRAPH_DEPTH = 10
MAX_CONTEXT_LINES = 20
MAX_FILE_RANGES = 10
MAX_RANGE_LINES = 200
MAX_EVIDENCE_BYTES = 256 * 1024
SOURCE_SEARCH_BYTES_PER_FILE = 256 * 1024
SOURCE_SEARCH_MAX_FILES = 500

_SOURCE_LOCATION = re.compile(r"^L?(\d+)(?:-L?(\d+))?$")


class RepositoryNavigator:
    """Read-only runtime surface over one exact Layers 1–5 repository state."""

    def __init__(
        self,
        context: RepositoryContext,
        file_index: FileIndex,
        symbol_index: SymbolIndex,
        graph_build: GraphBuildResult,
        overlay: GraphEnrichmentOverlay | None = None,
    ) -> None:
        """Initialize navigation over mutually compatible immutable authorities."""
        self._validate_authorities(context, file_index, symbol_index, graph_build)
        if (
            overlay is not None
            and overlay.graph_snapshot_id != graph_build.manifest.snapshot_id
        ):
            raise ValueError("enrichment overlay belongs to a different graph snapshot")

        self._context = context
        self._file_index = file_index
        self._symbol_index = symbol_index
        self._graph_build = graph_build
        self._graph = graph_build.graph
        self._structural = load_graph_snapshot_structural_state(graph_build)
        self._files_by_path = {record.path: record for record in file_index.files}
        self._symbols_by_id = {
            symbol.symbol_id: symbol for symbol in symbol_index.symbols
        }
        self._node_communities = {
            node_id: community_id
            for community_id, members in self._communities.items()
            for node_id in members
        }
        self._hyperedges_by_id = self._index_hyperedges()
        self._enrichment = self._index_enrichment(overlay)
        self._node_symbol_ids = {
            node_id: [
                symbol.symbol_id for symbol in self._match_symbols_for_node(node_id)
            ]
            for node_id in self._graph.nodes
        }
        self._symbol_node_ids = {
            symbol.symbol_id: [
                node_id
                for node_id in self._graph.nodes
                if symbol.symbol_id in self._node_symbol_ids[node_id]
            ]
            for symbol in symbol_index.symbols
        }

    @property
    def _communities(self) -> dict[int, list[str]]:
        return cast(dict[int, list[str]], self._structural["communities"])

    def search_repository(
        self,
        query: str,
        *,
        kinds: Iterable[RepositorySearchKind] | None = None,
        limit: int = DEFAULT_RESULT_LIMIT,
        min_score: float = 40,
    ) -> list[RepositorySearchHit]:
        """Search existing entities with bounded deterministic lexical matching."""
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must be non-empty")
        limit = _bounded("limit", limit, maximum=MAX_RESULT_LIMIT)
        if not 0 <= min_score <= 100:
            raise ValueError("min_score must be between 0 and 100")
        selected_kinds = set(kinds) if kinds is not None else set(_all_search_kinds())
        if not selected_kinds <= set(_all_search_kinds()):
            raise ValueError("search includes an unsupported repository entity kind")

        hits = [
            hit
            for hit in self._structured_search_candidates(normalized_query)
            if hit.kind in selected_kinds and (hit.score or 0) >= min_score
        ]
        hits.sort(
            key=lambda hit: (
                -(hit.score or 0),
                hit.kind,
                hit.label.casefold(),
                _canonical_ref(hit.ref),
            )
        )
        return hits[:limit]

    def get_graph_entity(
        self,
        target_type: EnrichmentTargetType,
        target_ref: EnrichmentTargetReference,
        *,
        max_members: int = DEFAULT_MAX_NODES,
    ) -> CompositeEntityView:
        """Inspect one existing graph entity with exactly matching enrichment."""
        max_members = _bounded("max_members", max_members, maximum=MAX_GRAPH_NODES)
        if target_type == "node":
            if not isinstance(target_ref, str):
                raise ValueError("node target_ref must be a node_id")
            return self._node_view(target_ref)
        if target_type == "edge":
            source, target, relation = _edge_identity(target_ref)
            return self._edge_view(source, target, relation)
        if target_type == "hyperedge":
            if not isinstance(target_ref, str):
                raise ValueError("hyperedge target_ref must be a hyperedge_id")
            return self._hyperedge_view(target_ref, max_members=max_members)
        if target_type == "community":
            community_id, member_signature = _community_identity(target_ref)
            return self._community_view(
                community_id,
                member_signature,
                max_members=max_members,
            )
        if target_type == "graph":
            if target_ref != "graph":
                raise ValueError('graph target_ref must be "graph"')
            return self._graph_view()
        raise ValueError(f"unsupported graph target type: {target_type}")

    def get_graph_neighbors(
        self,
        node_id: str,
        *,
        direction: GraphDirection = "both",
        relations: Iterable[str] | None = None,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
        max_hyperedges: int = DEFAULT_MAX_HYPEREDGES,
    ) -> GraphTraversalView:
        """Return a bounded one-hop neighborhood with incoming/outgoing relations."""
        self._require_node(node_id)
        max_nodes, max_edges, max_hyperedges = _graph_limits(
            max_nodes, max_edges, max_hyperedges
        )
        relation_filter = _relation_filter(relations)
        candidates = self._incident_edges(node_id, direction, relation_filter)
        selected_edges: list[tuple[str, str, str]] = []
        selected_nodes = [node_id]
        seen_nodes = {node_id}
        truncated = False
        for source, target, relation in candidates:
            neighbor = target if source == node_id else source
            if neighbor not in seen_nodes and len(selected_nodes) >= max_nodes:
                truncated = True
                continue
            if len(selected_edges) >= max_edges:
                truncated = True
                break
            if neighbor not in seen_nodes:
                seen_nodes.add(neighbor)
                selected_nodes.append(neighbor)
            selected_edges.append((source, target, relation))
        hyperedges, hyperedges_truncated = self._hyperedges_for_nodes(
            seen_nodes, max_hyperedges
        )
        return GraphTraversalView(
            nodes=[self._node_view(value) for value in selected_nodes],
            edges=[self._edge_view(*edge) for edge in selected_edges],
            hyperedges=hyperedges,
            truncated=truncated or hyperedges_truncated,
        )

    def get_graph_path(
        self,
        source_node_id: str,
        target_node_id: str,
        *,
        direction: GraphDirection = "outgoing",
        relations: Iterable[str] | None = None,
        max_depth: int = MAX_GRAPH_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
    ) -> GraphTraversalView | None:
        """Return one bounded deterministic shortest path, or None when absent."""
        self._require_node(source_node_id)
        self._require_node(target_node_id)
        _require_direction(direction)
        max_depth = _bounded("max_depth", max_depth, maximum=MAX_GRAPH_DEPTH)
        max_nodes = _bounded("max_nodes", max_nodes, maximum=MAX_GRAPH_NODES)
        relation_filter = _relation_filter(relations)
        queue: deque[list[str]] = deque([[source_node_id]])
        visited = {source_node_id}
        truncated = False
        path: list[str] | None = None
        while queue:
            candidate = queue.popleft()
            current = candidate[-1]
            if current == target_node_id:
                path = candidate
                break
            if len(candidate) - 1 >= max_depth:
                truncated = True
                continue
            for neighbor in self._adjacent_nodes(current, direction, relation_filter):
                if neighbor in visited:
                    continue
                if len(visited) >= max_nodes:
                    truncated = True
                    continue
                visited.add(neighbor)
                queue.append([*candidate, neighbor])
        if path is None:
            return None
        path_edges = [
            self._edge_between(path[index], path[index + 1], direction, relation_filter)
            for index in range(len(path) - 1)
        ]
        return GraphTraversalView(
            nodes=[self._node_view(node_id) for node_id in path],
            edges=[self._edge_view(*edge) for edge in path_edges],
            hyperedges=[],
            truncated=truncated,
        )

    def get_graph_subgraph(
        self,
        node_id: str,
        *,
        depth: int = 2,
        direction: GraphDirection = "both",
        relations: Iterable[str] | None = None,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
        max_hyperedges: int = DEFAULT_MAX_HYPEREDGES,
    ) -> GraphTraversalView:
        """Materialize a bounded breadth-first neighborhood around one node."""
        self._require_node(node_id)
        _require_direction(direction)
        depth = _bounded("depth", depth, maximum=MAX_GRAPH_DEPTH)
        max_nodes, max_edges, max_hyperedges = _graph_limits(
            max_nodes, max_edges, max_hyperedges
        )
        relation_filter = _relation_filter(relations)
        selected_nodes = [node_id]
        seen_nodes = {node_id}
        selected_edges: list[tuple[str, str, str]] = []
        seen_edges: set[tuple[str, str, str]] = set()
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        truncated = False
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in self._incident_edges(current, direction, relation_filter):
                if edge not in seen_edges and len(selected_edges) >= max_edges:
                    truncated = True
                    queue.clear()
                    break
                source, target, _relation = edge
                neighbor = target if source == current else source
                if neighbor not in seen_nodes:
                    if len(selected_nodes) >= max_nodes:
                        truncated = True
                        continue
                    seen_nodes.add(neighbor)
                    selected_nodes.append(neighbor)
                    queue.append((neighbor, current_depth + 1))
                if edge not in seen_edges:
                    seen_edges.add(edge)
                    selected_edges.append(edge)
        hyperedges, hyperedges_truncated = self._hyperedges_for_nodes(
            seen_nodes, max_hyperedges
        )
        return GraphTraversalView(
            nodes=[self._node_view(value) for value in selected_nodes],
            edges=[self._edge_view(*edge) for edge in selected_edges],
            hyperedges=hyperedges,
            truncated=truncated or hyperedges_truncated,
        )

    def get_graph_community(
        self,
        community_id: int,
        *,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
    ) -> GraphCommunityView:
        """Return bounded members and internal/cross-community connections."""
        max_nodes = _bounded("max_nodes", max_nodes, maximum=MAX_GRAPH_NODES)
        max_edges = _bounded("max_edges", max_edges, maximum=MAX_GRAPH_EDGES)
        members = self._communities.get(community_id)
        if members is None:
            raise KeyError(f"unknown graph community: {community_id}")
        member_set = set(members)
        selected_members = sorted(members)[:max_nodes]
        internal: list[tuple[str, str, str]] = []
        cross: list[tuple[str, str, str]] = []
        truncated = len(selected_members) < len(members)
        for source, target, attributes in sorted(
            self._graph.edges(data=True), key=_edge_data_sort_key
        ):
            source_inside = source in member_set
            target_inside = target in member_set
            if not source_inside and not target_inside:
                continue
            edge = (source, target, str(attributes.get("relation", "")))
            bucket = internal if source_inside and target_inside else cross
            if len(internal) + len(cross) >= max_edges:
                truncated = True
                break
            bucket.append(edge)
        signature = self._community_signature(community_id)
        return GraphCommunityView(
            community=self._community_view(
                community_id, signature, max_members=max_nodes
            ),
            members=[self._node_view(node_id) for node_id in selected_members],
            internal_edges=[self._edge_view(*edge) for edge in internal],
            cross_community_edges=[self._edge_view(*edge) for edge in cross],
            truncated=truncated,
        )

    def get_graph_central_nodes(
        self, *, limit: int = DEFAULT_RESULT_LIMIT
    ) -> list[CompositeEntityView]:
        """Return persisted Layer 4 god nodes in their deterministic order."""
        limit = _bounded("limit", limit, maximum=MAX_RESULT_LIMIT)
        central_nodes = cast(list[dict[str, Any]], self._structural["god_nodes"])
        return [self._node_view(str(record["id"])) for record in central_nodes[:limit]]

    def graph_to_file(self, node_id: str) -> FileRecord | None:
        """Resolve a graph node's deterministic source_file through FileIndex."""
        self._require_node(node_id)
        source_path = self._graph.nodes[node_id].get("source_file")
        if not isinstance(source_path, str) or not source_path:
            return None
        return self._files_by_path.get(source_path)

    def graph_to_symbols(self, node_id: str) -> list[SymbolRecord]:
        """Return every symbol deterministically associated with a graph node."""
        self._require_node(node_id)
        return [
            self._symbols_by_id[symbol_id]
            for symbol_id in self._node_symbol_ids[node_id]
        ]

    def file_to_graph(self, path: str) -> list[str]:
        """Return every graph node with an exact source_file association."""
        self._require_file(path)
        return sorted(
            node_id
            for node_id, attributes in self._graph.nodes(data=True)
            if attributes.get("source_file") == path
        )

    def symbol_to_graph(self, symbol_id: str) -> list[str]:
        """Return all exact deterministic graph associations for one symbol."""
        self._require_symbol(symbol_id)
        return list(self._symbol_node_ids[symbol_id])

    def list_files(
        self,
        *,
        path_prefix: str | None = None,
        content_types: Iterable[str] | None = None,
        read_modes: Iterable[str] | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
    ) -> list[FileRecord]:
        """List a bounded filtered view of the canonical FileIndex."""
        limit = _bounded("limit", limit, maximum=MAX_LIST_LIMIT)
        selected_content_types = (
            set(content_types) if content_types is not None else None
        )
        selected_read_modes = set(read_modes) if read_modes is not None else None
        return [
            record
            for record in self._file_index.files
            if (path_prefix is None or record.path.startswith(path_prefix))
            and (
                selected_content_types is None
                or record.content_type in selected_content_types
            )
            and (
                selected_read_modes is None
                or record.disposition.read_mode in selected_read_modes
            )
        ][:limit]

    def get_file_overview(
        self,
        path: str,
        *,
        max_symbols: int = DEFAULT_LIST_LIMIT,
        max_graph_nodes: int = DEFAULT_LIST_LIMIT,
    ) -> FileOverview:
        """Return one FileRecord with bounded exact symbol and graph associations."""
        record = self._require_file(path)
        max_symbols = _bounded("max_symbols", max_symbols, maximum=MAX_LIST_LIMIT)
        max_graph_nodes = _bounded(
            "max_graph_nodes", max_graph_nodes, maximum=MAX_GRAPH_NODES
        )
        symbol_ids = [
            symbol.symbol_id
            for symbol in self._symbol_index.symbols
            if symbol.path == path
        ]
        graph_node_ids = self.file_to_graph(path)
        return FileOverview(
            file=record,
            symbol_ids=symbol_ids[:max_symbols],
            graph_node_ids=graph_node_ids[:max_graph_nodes],
            symbols_truncated=len(symbol_ids) > max_symbols,
            graph_nodes_truncated=len(graph_node_ids) > max_graph_nodes,
        )

    def list_symbols(
        self,
        *,
        path: str | None = None,
        kinds: Iterable[SymbolKind] | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
    ) -> list[SymbolRecord]:
        """List bounded canonical SymbolIndex records."""
        limit = _bounded("limit", limit, maximum=MAX_LIST_LIMIT)
        if path is not None:
            self._require_file(path)
        selected_kinds = set(kinds) if kinds is not None else None
        return [
            symbol
            for symbol in self._symbol_index.symbols
            if (path is None or symbol.path == path)
            and (selected_kinds is None or symbol.kind in selected_kinds)
        ][:limit]

    def search_symbols(
        self,
        query: str,
        *,
        path: str | None = None,
        kinds: Iterable[SymbolKind] | None = None,
        limit: int = DEFAULT_RESULT_LIMIT,
        min_score: float = 40,
    ) -> list[SymbolRecord]:
        """Search exact indexed symbol names with deterministic fuzzy ranking."""
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must be non-empty")
        limit = _bounded("limit", limit, maximum=MAX_RESULT_LIMIT)
        if not 0 <= min_score <= 100:
            raise ValueError("min_score must be between 0 and 100")
        if path is not None:
            self._require_file(path)
        selected_kinds = set(kinds) if kinds is not None else None
        candidates = [
            symbol
            for symbol in self._symbol_index.symbols
            if (path is None or symbol.path == path)
            and (selected_kinds is None or symbol.kind in selected_kinds)
        ]
        scored = [
            (
                _lexical_score(
                    normalized_query,
                    [symbol.name, symbol.qualified_name or "", symbol.signature or ""],
                ),
                symbol,
            )
            for symbol in candidates
        ]
        scored.sort(key=lambda item: (-item[0], _symbol_sort_key(item[1])))
        return [symbol for score, symbol in scored if score >= min_score][:limit]

    def search_source_content(
        self,
        query: str,
        *,
        regex: bool = False,
        paths: Iterable[str] | None = None,
        context_lines: int = 2,
        limit: int = DEFAULT_RESULT_LIMIT,
        max_files: int = SOURCE_SEARCH_MAX_FILES,
    ) -> list[SourceContentMatch]:
        """Search authorized repository text separately from structured search."""
        if not query:
            raise ValueError("query must be non-empty")
        context_lines = _bounded(
            "context_lines", context_lines, maximum=MAX_CONTEXT_LINES, allow_zero=True
        )
        limit = _bounded("limit", limit, maximum=MAX_RESULT_LIMIT)
        max_files = _bounded("max_files", max_files, maximum=SOURCE_SEARCH_MAX_FILES)
        selected_paths = set(paths) if paths is not None else None
        if selected_paths is not None:
            for path in selected_paths:
                self._require_file(path)
        pattern = re.compile(query, re.IGNORECASE) if regex else None
        matches: list[SourceContentMatch] = []
        searchable_files = [
            record
            for record in self._file_index.files
            if (selected_paths is None or record.path in selected_paths)
            and record.disposition.read_mode != "denied"
            and record.disposition.processing_mode != "skip"
            and record.content_type != "binary"
        ][:max_files]
        for record in searchable_files:
            source = read_file(
                self._context,
                self._file_index,
                SourceReadRequest(
                    path=record.path,
                    max_bytes=SOURCE_SEARCH_BYTES_PER_FILE,
                ),
            )
            lines = source.content.splitlines()
            for index, line in enumerate(lines):
                matched = (
                    bool(pattern.search(line))
                    if pattern
                    else query.casefold() in line.casefold()
                )
                if not matched:
                    continue
                context_start = max(0, index - context_lines)
                context_end = min(len(lines), index + context_lines + 1)
                matches.append(
                    SourceContentMatch(
                        path=record.path,
                        line_number=index + 1,
                        line_text=line,
                        context_start_line=context_start + 1,
                        context_end_line=max(context_start + 1, context_end),
                        context="\n".join(lines[context_start:context_end]),
                        source_truncated=source.truncated,
                    )
                )
                if len(matches) >= limit:
                    return matches
        return matches

    def read_symbol_excerpt(
        self,
        symbol_id: str,
        *,
        context_lines: int = 2,
        max_bytes: int = 64 * 1024,
    ) -> SourceReadResult:
        """Read a bounded declaration excerpt through Layer 1 source policy."""
        symbol = self._require_symbol(symbol_id)
        context_lines = _bounded(
            "context_lines", context_lines, maximum=MAX_CONTEXT_LINES, allow_zero=True
        )
        max_bytes = _bounded("max_bytes", max_bytes, maximum=MAX_EVIDENCE_BYTES)
        start_line = max(1, symbol.start_line - context_lines)
        requested_end = symbol.end_line + context_lines
        capped_end = min(requested_end, start_line + MAX_RANGE_LINES - 1)
        result = self._read_clamped_range(
            symbol.path, start_line, capped_end, max_bytes=max_bytes
        )
        if capped_end < requested_end:
            result = result.model_copy(update={"truncated": True})
        return result

    def read_file_ranges(
        self,
        path: str,
        ranges: Sequence[tuple[int, int]],
        *,
        max_bytes_per_range: int = 64 * 1024,
    ) -> list[SourceReadResult]:
        """Read bounded exact line ranges through the Layer 1 source reader."""
        self._require_file(path)
        if not ranges or len(ranges) > MAX_FILE_RANGES:
            raise ValueError(
                f"ranges must contain between 1 and {MAX_FILE_RANGES} items"
            )
        max_bytes_per_range = _bounded(
            "max_bytes_per_range",
            max_bytes_per_range,
            maximum=MAX_EVIDENCE_BYTES,
        )
        results: list[SourceReadResult] = []
        for start_line, end_line in ranges:
            if start_line < 1 or end_line < start_line:
                raise ValueError("file ranges must be positive and non-inverted")
            if end_line - start_line + 1 > MAX_RANGE_LINES:
                raise ValueError(
                    f"each file range is limited to {MAX_RANGE_LINES} lines"
                )
            results.append(
                self._read_clamped_range(
                    path,
                    start_line,
                    end_line,
                    max_bytes=max_bytes_per_range,
                )
            )
        return results

    def read_around_match(
        self,
        path: str,
        line_number: int,
        *,
        context_lines: int = 5,
        max_bytes: int = 64 * 1024,
    ) -> SourceReadResult:
        """Read a bounded exact-source window around one line-addressable match."""
        self._require_file(path)
        if line_number < 1:
            raise ValueError("line_number must be positive")
        context_lines = _bounded(
            "context_lines", context_lines, maximum=MAX_CONTEXT_LINES, allow_zero=True
        )
        max_bytes = _bounded("max_bytes", max_bytes, maximum=MAX_EVIDENCE_BYTES)
        return self._read_clamped_range(
            path,
            max(1, line_number - context_lines),
            line_number + context_lines,
            max_bytes=max_bytes,
        )

    def _structured_search_candidates(self, query: str) -> list[RepositorySearchHit]:
        hits: list[RepositorySearchHit] = []
        for node_id, attributes in self._graph.nodes(data=True):
            label = str(attributes.get("label") or node_id)
            source_path = _existing_source_path(attributes, self._files_by_path)
            fields = [
                label,
                node_id,
                source_path or "",
                *_searchable_values(attributes),
            ]
            fields.extend(self._enrichment_search_values("node", node_id))
            hits.append(
                RepositorySearchHit(
                    kind="node",
                    ref=node_id,
                    label=label,
                    source_path=source_path,
                    score=_lexical_score(query, fields),
                )
            )
        for community_id in sorted(self._communities):
            target_ref = self._community_ref(community_id)
            deterministic_label = str(
                cast(dict[int, str], self._structural["community_labels"])[community_id]
            )
            enrichment_values = self._enrichment_search_values("community", target_ref)
            ai_name = self._community_name(target_ref)
            hits.append(
                RepositorySearchHit(
                    kind="community",
                    ref=target_ref,
                    label=ai_name or deterministic_label,
                    score=_lexical_score(
                        query,
                        [
                            deterministic_label,
                            str(community_id),
                            *enrichment_values,
                        ],
                    ),
                )
            )
        for hyperedge_id, hyperedge in sorted(self._hyperedges_by_id.items()):
            label = str(hyperedge.get("label") or hyperedge_id)
            source_path = _existing_source_path(hyperedge, self._files_by_path)
            hits.append(
                RepositorySearchHit(
                    kind="hyperedge",
                    ref=hyperedge_id,
                    label=label,
                    source_path=source_path,
                    score=_lexical_score(
                        query,
                        [
                            label,
                            hyperedge_id,
                            source_path or "",
                            *_searchable_values(hyperedge),
                            *self._enrichment_search_values("hyperedge", hyperedge_id),
                        ],
                    ),
                )
            )
        for record in self._file_index.files:
            hits.append(
                RepositorySearchHit(
                    kind="file",
                    ref=record.path,
                    label=record.path,
                    source_path=record.path,
                    score=_lexical_score(query, [record.path, record.language or ""]),
                )
            )
        for symbol in self._symbol_index.symbols:
            hits.append(
                RepositorySearchHit(
                    kind="symbol",
                    ref=symbol.symbol_id,
                    label=symbol.qualified_name or symbol.name,
                    source_path=symbol.path,
                    score=_lexical_score(
                        query,
                        [symbol.name, symbol.qualified_name or "", symbol.path],
                    ),
                )
            )
        return hits

    def _compose(
        self,
        target_type: EnrichmentTargetType,
        target_ref: EnrichmentTargetReference,
        deterministic: dict[str, Any],
    ) -> CompositeEntityView:
        records = self._enrichment.get((target_type, _canonical_ref(target_ref)), [])
        return CompositeEntityView(
            target_type=target_type,
            target_ref=deepcopy(target_ref),
            deterministic=deepcopy(deterministic),
            enrichment=[record.model_copy(deep=True) for record in records],
        )

    def _node_view(self, node_id: str) -> CompositeEntityView:
        self._require_node(node_id)
        return self._compose(
            "node",
            node_id,
            {
                "node_id": node_id,
                "attributes": deepcopy(dict(self._graph.nodes[node_id])),
                "in_degree": self._graph.in_degree(node_id),
                "out_degree": self._graph.out_degree(node_id),
                "community_id": self._node_communities.get(node_id),
            },
        )

    def _edge_view(
        self, source: str, target: str, relation: str
    ) -> CompositeEntityView:
        if not self._graph.has_edge(source, target):
            raise KeyError(f"unknown graph edge: {source} -> {target}")
        attributes = dict(self._graph[source][target])
        if attributes.get("relation") != relation:
            raise KeyError(
                f"unknown graph edge relation: {source} -> {target} {relation}"
            )
        target_ref: dict[str, JsonValue] = {
            "source_node_id": source,
            "target_node_id": target,
            "relation": relation,
        }
        return self._compose(
            "edge",
            target_ref,
            {**target_ref, "attributes": deepcopy(attributes)},
        )

    def _hyperedge_view(
        self, hyperedge_id: str, *, max_members: int
    ) -> CompositeEntityView:
        hyperedge = self._hyperedges_by_id.get(hyperedge_id)
        if hyperedge is None:
            raise KeyError(f"unknown graph hyperedge: {hyperedge_id}")
        deterministic = deepcopy(hyperedge)
        members = deterministic.get("nodes")
        if isinstance(members, list):
            deterministic["member_count"] = len(members)
            deterministic["nodes"] = members[:max_members]
            deterministic["members_truncated"] = len(members) > max_members
        return self._compose("hyperedge", hyperedge_id, deterministic)

    def _community_view(
        self,
        community_id: int,
        member_signature: str,
        *,
        max_members: int,
    ) -> CompositeEntityView:
        members = self._communities.get(community_id)
        if members is None:
            raise KeyError(f"unknown graph community: {community_id}")
        if self._community_signature(community_id) != member_signature:
            raise KeyError("community member_signature does not match structural state")
        target_ref: dict[str, JsonValue] = {
            "community_id": community_id,
            "member_signature": member_signature,
        }
        labels = cast(dict[int, str], self._structural["community_labels"])
        cohesion = cast(dict[int, float], self._structural["cohesion"])
        return self._compose(
            "community",
            target_ref,
            {
                **target_ref,
                "deterministic_label": labels[community_id],
                "cohesion": cohesion[community_id],
                "member_count": len(members),
                "members": sorted(members)[:max_members],
                "members_truncated": len(members) > max_members,
            },
        )

    def _graph_view(self) -> CompositeEntityView:
        metadata = {
            key: deepcopy(value)
            for key, value in self._graph.graph.items()
            if key != "hyperedges"
        }
        return self._compose(
            "graph",
            "graph",
            {
                "metadata": metadata,
                "node_count": self._graph.number_of_nodes(),
                "edge_count": self._graph.number_of_edges(),
                "hyperedge_count": len(self._hyperedges_by_id),
                "community_count": len(self._communities),
                "god_nodes": deepcopy(self._structural["god_nodes"]),
                "surprising_connections": deepcopy(
                    self._structural["surprising_connections"]
                ),
                "suggested_questions": deepcopy(
                    self._structural["suggested_questions"]
                ),
            },
        )

    def _incident_edges(
        self,
        node_id: str,
        direction: GraphDirection,
        relations: set[str] | None,
    ) -> list[tuple[str, str, str]]:
        _require_direction(direction)
        edges: set[tuple[str, str, str]] = set()
        if direction in {"outgoing", "both"}:
            for _source, target, attributes in self._graph.out_edges(
                node_id, data=True
            ):
                relation = str(attributes.get("relation", ""))
                if relations is None or relation in relations:
                    edges.add((node_id, target, relation))
        if direction in {"incoming", "both"}:
            for source, _target, attributes in self._graph.in_edges(node_id, data=True):
                relation = str(attributes.get("relation", ""))
                if relations is None or relation in relations:
                    edges.add((source, node_id, relation))
        return sorted(edges)

    def _adjacent_nodes(
        self,
        node_id: str,
        direction: GraphDirection,
        relations: set[str] | None,
    ) -> list[str]:
        return sorted(
            {
                target if source == node_id else source
                for source, target, _relation in self._incident_edges(
                    node_id, direction, relations
                )
            }
        )

    def _edge_between(
        self,
        first: str,
        second: str,
        direction: GraphDirection,
        relations: set[str] | None,
    ) -> tuple[str, str, str]:
        candidates: list[tuple[str, str, str]] = []
        endpoint_pairs = {
            "outgoing": ((first, second),),
            "incoming": ((second, first),),
            "both": ((first, second), (second, first)),
        }[direction]
        for source, target in endpoint_pairs:
            if self._graph.has_edge(source, target):
                relation = str(self._graph[source][target].get("relation", ""))
                if relations is None or relation in relations:
                    candidates.append((source, target, relation))
        if not candidates:
            raise KeyError(f"path contains no matching edge: {first}, {second}")
        return sorted(candidates)[0]

    def _hyperedges_for_nodes(
        self, node_ids: set[str], limit: int
    ) -> tuple[list[CompositeEntityView], bool]:
        matching = [
            hyperedge_id
            for hyperedge_id, hyperedge in sorted(self._hyperedges_by_id.items())
            if isinstance(hyperedge.get("nodes"), list)
            and node_ids.intersection(cast(list[str], hyperedge["nodes"]))
        ]
        return (
            [
                self._hyperedge_view(hyperedge_id, max_members=DEFAULT_MAX_NODES)
                for hyperedge_id in matching[:limit]
            ],
            len(matching) > limit,
        )

    def _read_clamped_range(
        self, path: str, start_line: int, end_line: int, *, max_bytes: int
    ) -> SourceReadResult:
        line_count = self._source_line_count(path)
        if start_line > line_count:
            raise RepositoryError(f"line range is outside file: {path}")
        return read_file(
            self._context,
            self._file_index,
            SourceReadRequest(
                path=path,
                start_line=start_line,
                end_line=min(end_line, line_count),
                max_bytes=max_bytes,
            ),
        )

    def _source_line_count(self, path: str) -> int:
        metadata_read = read_file(
            self._context,
            self._file_index,
            SourceReadRequest(path=path, max_bytes=1),
        )
        return metadata_read.end_line

    def _match_symbols_for_node(self, node_id: str) -> list[SymbolRecord]:
        attributes = self._graph.nodes[node_id]
        source_path = attributes.get("source_file")
        if not isinstance(source_path, str) or source_path not in self._files_by_path:
            return []
        candidates = [
            symbol
            for symbol in self._symbol_index.symbols
            if symbol.path == source_path
        ]
        if not candidates or _is_file_node(attributes, source_path):
            return []

        source_range = _node_source_range(attributes)
        if source_range is not None:
            start_line, end_line = source_range
            range_matches = [
                symbol
                for symbol in candidates
                if symbol.start_line == start_line
                and (end_line is None or symbol.end_line == end_line)
            ]
            if range_matches:
                return sorted(range_matches, key=_symbol_sort_key)

        qualified_name = _node_text(attributes, "qualified_name")
        if qualified_name:
            qualified_matches = [
                symbol
                for symbol in candidates
                if symbol.qualified_name == qualified_name
            ]
            if qualified_matches:
                return sorted(qualified_matches, key=_symbol_sort_key)

        name = _node_text(attributes, "name") or _normalized_node_label(
            attributes.get("label")
        )
        if not name:
            return []
        kind = (
            _node_text(attributes, "symbol_kind")
            or _node_text(attributes, "kind")
            or _node_text(attributes, "node_type")
        )
        name_matches = [
            symbol
            for symbol in candidates
            if symbol.name == name and (kind is None or symbol.kind == kind)
        ]
        return sorted(name_matches, key=_symbol_sort_key)

    def _index_hyperedges(self) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for value in self._graph.graph.get("hyperedges", []):
            if not isinstance(value, dict) or not isinstance(value.get("id"), str):
                continue
            indexed[value["id"]] = value
        return indexed

    @staticmethod
    def _index_enrichment(
        overlay: GraphEnrichmentOverlay | None,
    ) -> dict[tuple[str, str], list[EnrichmentRecord]]:
        indexed: dict[tuple[str, str], list[EnrichmentRecord]] = {}
        if overlay is None:
            return indexed
        for record in overlay.records:
            key = (record.target_type, _canonical_ref(record.target_ref))
            indexed.setdefault(key, []).append(record)
        return indexed

    def _enrichment_search_values(
        self,
        target_type: EnrichmentTargetType,
        target_ref: EnrichmentTargetReference,
    ) -> list[str]:
        values: list[str] = []
        for record in self._enrichment.get(
            (target_type, _canonical_ref(target_ref)), []
        ):
            values.append(record.annotation_type)
            values.extend(_searchable_values(record.value))
        return values

    def _community_name(self, target_ref: EnrichmentTargetReference) -> str | None:
        for record in self._enrichment.get(
            ("community", _canonical_ref(target_ref)), []
        ):
            if (
                record.annotation_type == "name"
                and isinstance(record.value, str)
                and record.value.strip()
            ):
                return record.value
        return None

    def _community_signature(self, community_id: int) -> str:
        signatures = cast(
            dict[int, str], self._structural["community_member_signatures"]
        )
        return signatures[community_id]

    def _community_ref(self, community_id: int) -> dict[str, Any]:
        return {
            "community_id": community_id,
            "member_signature": self._community_signature(community_id),
        }

    def _require_node(self, node_id: str) -> None:
        if node_id not in self._graph:
            raise KeyError(f"unknown graph node: {node_id}")

    def _require_file(self, path: str) -> FileRecord:
        record = self._files_by_path.get(path)
        if record is None:
            raise RepositoryError(f"path is absent from the FileIndex: {path}")
        return record

    def _require_symbol(self, symbol_id: str) -> SymbolRecord:
        symbol = self._symbols_by_id.get(symbol_id)
        if symbol is None:
            raise KeyError(f"unknown symbol: {symbol_id}")
        return symbol

    @staticmethod
    def _validate_authorities(
        context: RepositoryContext,
        file_index: FileIndex,
        symbol_index: SymbolIndex,
        graph_build: GraphBuildResult,
    ) -> None:
        expected_identity = (
            context.repository_id,
            context.revision,
            context.scope_path,
        )
        if (
            file_index.repository_id,
            file_index.revision,
            file_index.scope_path,
        ) != expected_identity:
            raise ValueError("FileIndex does not belong to RepositoryContext")
        if (
            symbol_index.repository_id,
            symbol_index.revision,
            symbol_index.scope_path,
        ) != expected_identity:
            raise ValueError("SymbolIndex does not belong to RepositoryContext")
        if (
            graph_build.manifest.repository_id,
            graph_build.manifest.revision,
            graph_build.manifest.scope_path,
        ) != expected_identity:
            raise ValueError("graph snapshot does not belong to RepositoryContext")
        validate_graph_snapshot(
            graph_build.snapshot_root,
            expected_context=context,
            expected_file_index=file_index,
        )


def _all_search_kinds() -> tuple[RepositorySearchKind, ...]:
    return ("node", "community", "hyperedge", "file", "symbol")


def _canonical_ref(target_ref: EnrichmentTargetReference) -> str:
    return json.dumps(
        target_ref, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _edge_identity(target_ref: EnrichmentTargetReference) -> tuple[str, str, str]:
    required = {"source_node_id", "target_node_id", "relation"}
    if not isinstance(target_ref, dict) or set(target_ref) != required:
        raise ValueError("edge target_ref requires source, target, and relation")
    values = tuple(target_ref[key] for key in sorted(required))
    if not all(isinstance(value, str) for value in values):
        raise ValueError("edge target_ref values must be strings")
    return (
        cast(str, target_ref["source_node_id"]),
        cast(str, target_ref["target_node_id"]),
        cast(str, target_ref["relation"]),
    )


def _community_identity(target_ref: EnrichmentTargetReference) -> tuple[int, str]:
    required = {"community_id", "member_signature"}
    if not isinstance(target_ref, dict) or set(target_ref) != required:
        raise ValueError(
            "community target_ref requires community_id and member_signature"
        )
    community_id = target_ref["community_id"]
    member_signature = target_ref["member_signature"]
    if (
        isinstance(community_id, bool)
        or not isinstance(community_id, int)
        or not isinstance(member_signature, str)
        or not member_signature
    ):
        raise ValueError("community target_ref is invalid")
    return community_id, member_signature


def _bounded(
    name: str,
    value: int,
    *,
    maximum: int,
    allow_zero: bool = False,
) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _graph_limits(
    max_nodes: int, max_edges: int, max_hyperedges: int
) -> tuple[int, int, int]:
    return (
        _bounded("max_nodes", max_nodes, maximum=MAX_GRAPH_NODES),
        _bounded("max_edges", max_edges, maximum=MAX_GRAPH_EDGES),
        _bounded("max_hyperedges", max_hyperedges, maximum=MAX_RESULT_LIMIT),
    )


def _require_direction(direction: GraphDirection) -> None:
    if direction not in {"incoming", "outgoing", "both"}:
        raise ValueError("direction must be incoming, outgoing, or both")


def _relation_filter(relations: Iterable[str] | None) -> set[str] | None:
    if relations is None:
        return None
    selected = set(relations)
    if any(not relation for relation in selected):
        raise ValueError("relation filters must be non-empty strings")
    return selected


def _lexical_score(query: str, fields: Iterable[str]) -> float:
    normalized_query = query.casefold().strip()
    score = 0.0
    for field in fields:
        normalized_field = field.casefold().strip()
        if not normalized_field:
            continue
        if normalized_field == normalized_query:
            candidate = 100.0
        elif normalized_field.startswith(normalized_query):
            candidate = 95.0
        elif normalized_query in normalized_field:
            candidate = 90.0
        else:
            candidate = float(WRatio(normalized_query, normalized_field))
        score = max(score, candidate)
    return round(score, 3)


def _searchable_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        values: list[str] = []
        for key, item in value.items():
            values.append(str(key))
            values.extend(_searchable_values(item))
        return values
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [text for item in value for text in _searchable_values(item)]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    return []


def _existing_source_path(
    attributes: Mapping[str, object], files_by_path: Mapping[str, FileRecord]
) -> str | None:
    source_path = attributes.get("source_file")
    if isinstance(source_path, str) and source_path in files_by_path:
        return source_path
    return None


def _node_source_range(
    attributes: Mapping[str, object],
) -> tuple[int, int | None] | None:
    start_line = attributes.get("start_line")
    end_line = attributes.get("end_line")
    if (
        isinstance(start_line, int)
        and not isinstance(start_line, bool)
        and start_line > 0
    ):
        if (
            isinstance(end_line, int)
            and not isinstance(end_line, bool)
            and end_line >= start_line
        ):
            return start_line, end_line
        return start_line, None
    source_location = attributes.get("source_location")
    if not isinstance(source_location, str):
        return None
    match = _SOURCE_LOCATION.fullmatch(source_location.strip())
    if match is None:
        return None
    parsed_start = int(match.group(1))
    parsed_end = int(match.group(2)) if match.group(2) else None
    if parsed_start < 1 or (parsed_end is not None and parsed_end < parsed_start):
        return None
    return parsed_start, parsed_end


def _node_text(attributes: Mapping[str, object], key: str) -> str | None:
    value = attributes.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    metadata = attributes.get("metadata")
    if isinstance(metadata, Mapping):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalized_node_label(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    label = value.strip()
    if label.startswith("."):
        label = label[1:]
    if label.endswith("()"):
        label = label[:-2]
    return label or None


def _is_file_node(attributes: Mapping[str, object], source_path: str) -> bool:
    label = attributes.get("label")
    if not isinstance(label, str):
        return False
    filename = source_path.rsplit("/", 1)[-1]
    stem = filename.rsplit(".", 1)[0]
    return label in {source_path, filename, stem}


def _edge_data_sort_key(
    edge: tuple[str, str, Mapping[str, object]],
) -> tuple[str, str, str]:
    source, target, attributes = edge
    return source, target, str(attributes.get("relation", ""))


def _symbol_sort_key(symbol: SymbolRecord) -> tuple[object, ...]:
    return (
        symbol.path,
        symbol.start_line,
        symbol.end_line,
        symbol.kind,
        symbol.qualified_name or "",
        symbol.name,
        symbol.symbol_id,
    )


__all__ = ["RepositoryNavigator"]
