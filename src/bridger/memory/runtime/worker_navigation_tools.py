"""Task-oriented repository tools for one memory-worker cycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)

from bridger.contracts.files import FileIndexPath
from bridger.contracts.memory.core import SourceBinding
from bridger.contracts.memory.worker_cycle import (
    EvidenceKind,
    EvidenceLocator,
    FileEvidenceLocator,
    GraphEntityEvidenceLocator,
    SourceRangeEvidenceLocator,
    SymbolEvidenceLocator,
)
from bridger.contracts.navigation import RepositorySearchHit
from bridger.llm.tools import LLMTool, ToolExecutionError, ToolExecutor
from bridger.navigation.navigator import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    MAX_RANGE_LINES,
    RepositoryNavigator,
)
from bridger.repository.errors import FileIndexPathMismatchError, RepositoryError

WORKER_REPOSITORY_TOOL_IDS = (
    "orient_repository",
    "inspect_graph_node",
    "inspect_graph_community",
    "trace_graph_path",
    "list_files",
    "inspect_file",
    "find_symbol",
    "inspect_symbol",
    "find_source_text",
    "read_source_range",
)


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    """One transient exact evidence identity bound to a worker context."""

    handle: str
    target_task_id: str
    source: SourceBinding
    kind: EvidenceKind
    locator: EvidenceLocator


class EvidenceCandidateRegistry:
    """Keep opaque evidence candidates for one active worker cycle."""

    def __init__(self, target_task_id: str, source: SourceBinding) -> None:
        self._target_task_id = target_task_id
        self._source = source
        self._candidates: dict[str, EvidenceCandidate] = {}

    def register(self, kind: EvidenceKind, locator: EvidenceLocator) -> str:
        """Register one exact locator and return its opaque transient handle."""
        handle = f"evidence-candidate-{uuid4().hex}"
        self._candidates[handle] = EvidenceCandidate(
            handle=handle,
            target_task_id=self._target_task_id,
            source=self._source,
            kind=kind,
            locator=locator,
        )
        return handle

    def resolve(self, handle: str) -> EvidenceCandidate:
        """Resolve one current-cycle handle or explain how to recover."""
        candidate = self._candidates.get(handle)
        if candidate is None:
            raise KeyError(
                "Unknown or expired evidence handle. Reinspect the repository "
                "location in the current cycle, then pass the returned handle to "
                "record_evidence."
            )
        if (
            candidate.target_task_id != self._target_task_id
            or candidate.source != self._source
        ):
            raise ValueError("evidence handle belongs to another target/source")
        return candidate

    def clear(self) -> None:
        """Discard every unrecorded or reusable handle at cycle termination."""
        self._candidates.clear()


def _repository_path_prefix(value: str) -> str:
    if (
        value.startswith("/")
        or value in {"", "."}
        or value.startswith("./")
        or value.endswith("/")
        or "/./" in value
        or "//" in value
        or ".." in value.split("/")
    ):
        raise ValueError("path_prefix must be a normalized repository-relative prefix")
    return value


RepositoryPathPrefix = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(_repository_path_prefix),
]


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _OrientRepositoryArguments(_Arguments):
    query: str = Field(min_length=1)


class _InspectGraphNodeArguments(_Arguments):
    node_id: str = Field(min_length=1)


class _InspectGraphCommunityArguments(_Arguments):
    community_id: int = Field(ge=0)


class _TraceGraphPathArguments(_Arguments):
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)


class _ListFilesArguments(_Arguments):
    path_prefix: RepositoryPathPrefix | None = None
    graph_node_id: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)

    @field_validator("graph_node_id")
    @classmethod
    def validate_selector(
        cls,
        graph_node_id: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if graph_node_id is not None and info.data.get("path_prefix") is not None:
            raise ValueError("path_prefix and graph_node_id are mutually exclusive")
        return graph_node_id


class _InspectFileArguments(_Arguments):
    path: FileIndexPath


class _FindSymbolArguments(_Arguments):
    query: str = Field(min_length=1)
    path: FileIndexPath | None = None


class _InspectSymbolArguments(_Arguments):
    symbol_id: str = Field(min_length=1)


class _FindSourceTextArguments(_Arguments):
    query: str = Field(min_length=1)
    paths: list[FileIndexPath] | None = None


class _ReadSourceRangeArguments(_Arguments):
    path: FileIndexPath
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @field_validator("end_line")
    @classmethod
    def validate_range(cls, end_line: int, info: ValidationInfo) -> int:
        start_line = info.data.get("start_line")
        if not isinstance(start_line, int):
            return end_line
        if end_line < start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        if end_line - start_line + 1 > MAX_RANGE_LINES:
            raise ValueError(f"line range is limited to {MAX_RANGE_LINES} lines")
        return end_line


class WorkerNavigationTools:
    """Compose semantic worker operations over a deterministic navigator."""

    def __init__(
        self,
        navigator: RepositoryNavigator,
        candidates: EvidenceCandidateRegistry,
    ) -> None:
        self._navigator = navigator
        self._candidates = candidates

    def orient_repository(self, query: str) -> dict[str, list[dict[str, object]]]:
        """Group structured orientation hits by their follow-up operation."""
        hits = self._navigator.search_repository(
            query,
            kinds=("node", "community", "file", "symbol"),
        )
        result: dict[str, list[dict[str, object]]] = {
            "graph_nodes": [],
            "communities": [],
            "files": [],
            "symbols": [],
        }
        for hit in hits:
            self._append_orientation_hit(result, hit)
        return result

    def inspect_graph_node(self, node_id: str) -> dict[str, object]:
        """Inspect one node, its neighborhood, and exact source bridges."""
        try:
            node = self._navigator.get_graph_entity("node", node_id)
        except KeyError as error:
            raise KeyError(
                "Unknown graph node ID. Use a node_id returned by "
                "orient_repository, inspect_graph_node, inspect_file, or "
                "inspect_symbol."
            ) from error
        neighborhood = self._navigator.get_graph_neighbors(node_id, direction="both")
        source_file = self._navigator.graph_to_file(node_id)
        symbols = self._navigator.graph_to_symbols(node_id)
        community_id = node.deterministic.get("community_id")
        handle = self._candidates.register(
            EvidenceKind.GRAPH_ENTITY,
            GraphEntityEvidenceLocator(target_type="node", target_ref=node_id),
        )
        return {
            "node": node,
            "relationships": {
                "neighboring_nodes": [
                    item for item in neighborhood.nodes if item.target_ref != node_id
                ],
                "edges": neighborhood.edges,
                "hyperedges": neighborhood.hyperedges,
                "truncated": neighborhood.truncated,
            },
            "source_bridges": {
                "files": [source_file] if source_file is not None else [],
                "symbols": symbols,
            },
            "communities": (
                [{"community_id": community_id}]
                if isinstance(community_id, int) and not isinstance(community_id, bool)
                else []
            ),
            "evidence_handle": handle,
        }

    def inspect_graph_community(self, community_id: int) -> dict[str, object]:
        """Inspect one bounded community and register its exact identity."""
        try:
            community = self._navigator.get_graph_community(community_id)
        except KeyError as error:
            raise KeyError(
                "Unknown graph community ID. Use a community_id returned by "
                "orient_repository or inspect_graph_node."
            ) from error
        target_ref = community.community.target_ref
        if not isinstance(target_ref, dict):
            raise ValueError("graph community returned an invalid identity")
        handle = self._candidates.register(
            EvidenceKind.GRAPH_ENTITY,
            GraphEntityEvidenceLocator(
                target_type="community",
                target_ref=target_ref,
            ),
        )
        return {
            "community": community.community,
            "members": community.members,
            "internal_relationships": community.internal_edges,
            "cross_community_relationships": community.cross_community_edges,
            "truncated": community.truncated,
            "evidence_handle": handle,
        }

    def trace_graph_path(
        self,
        source_node_id: str,
        target_node_id: str,
    ) -> object:
        """Trace a bounded shortest path while retaining actual edge direction."""
        try:
            return self._navigator.get_graph_path(
                source_node_id,
                target_node_id,
                direction="both",
            )
        except KeyError as error:
            raise KeyError(
                "Unknown graph node ID. Use node IDs returned by repository or graph "
                "inspection tools."
            ) from error

    def list_files(
        self,
        path_prefix: str | None,
        graph_node_id: str | None,
        limit: int,
    ) -> object:
        """List a bounded FileIndex slice by path area or graph neighborhood."""
        return self._navigator.list_files(
            path_prefix=path_prefix,
            graph_node_id=graph_node_id,
            limit=limit,
        )

    def inspect_file(self, path: FileIndexPath) -> dict[str, object]:
        """Inspect one file and expose its symbol and graph bridges."""
        try:
            overview = self._navigator.get_file_overview(path)
            symbols = self._navigator.list_symbols(path=path)
        except FileIndexPathMismatchError as error:
            raise _path_mismatch_tool_error(error) from error
        except RepositoryError as error:
            raise ValueError(
                "Repository path is not indexed/readable. Use a path returned by "
                "orient_repository, list_files, find_symbol, or find_source_text."
            ) from error
        handle = self._candidates.register(
            EvidenceKind.FILE,
            FileEvidenceLocator(path=overview.file.path),
        )
        return {
            "file": overview.file,
            "symbols": symbols,
            "symbols_truncated": overview.symbols_truncated,
            "graph_node_ids": overview.graph_node_ids,
            "graph_nodes_truncated": overview.graph_nodes_truncated,
            "evidence_handle": handle,
        }

    def find_symbol(self, query: str, path: FileIndexPath | None) -> object:
        """Find bounded indexed symbol matches by a known or suspected name."""
        try:
            return self._navigator.search_symbols(query, path=path)
        except FileIndexPathMismatchError as error:
            raise _path_mismatch_tool_error(error) from error
        except RepositoryError as error:
            raise ValueError(
                "Repository path is not indexed. Use a path returned by a repository "
                "tool or omit path to search all indexed symbols."
            ) from error

    def inspect_symbol(self, symbol_id: str) -> dict[str, object]:
        """Read exact bounded symbol source and expose graph associations."""
        try:
            source = self._navigator.read_symbol_excerpt(symbol_id)
            graph_node_ids = self._navigator.symbol_to_graph(symbol_id)
        except KeyError as error:
            raise KeyError(
                "Unknown symbol ID. Use a symbol_id returned by orient_repository, "
                "inspect_file, find_symbol, or inspect_graph_node."
            ) from error
        handle = self._candidates.register(
            EvidenceKind.SYMBOL,
            SymbolEvidenceLocator(symbol_id=symbol_id),
        )
        return {
            "symbol_id": symbol_id,
            "path": source.path,
            "start_line": source.start_line,
            "end_line": source.end_line,
            "revision": source.revision,
            "content": source.content,
            "truncated": source.truncated,
            "graph_node_ids": graph_node_ids,
            "evidence_handle": handle,
        }

    def find_source_text(
        self,
        query: str,
        paths: list[FileIndexPath] | None,
    ) -> object:
        """Search bounded literal source text and return line-addressable matches."""
        try:
            return self._navigator.search_source_content(
                query,
                regex=False,
                paths=paths,
            )
        except FileIndexPathMismatchError as error:
            raise _path_mismatch_tool_error(error) from error
        except RepositoryError as error:
            raise ValueError(
                "A repository path is not indexed/readable. Use paths returned by "
                "repository tools or omit paths to search readable source."
            ) from error

    def read_source_range(
        self,
        path: FileIndexPath,
        start_line: int,
        end_line: int,
    ) -> dict[str, object]:
        """Read one exact source range and register its authoritative locator."""
        try:
            source = self._navigator.read_file_ranges(
                path,
                [(start_line, end_line)],
            )[0]
        except FileIndexPathMismatchError as error:
            raise _path_mismatch_tool_error(error) from error
        except RepositoryError as error:
            raise ValueError(
                "Repository path or range is not indexed/readable. Use a path and "
                "line range returned by repository inspection or source search."
            ) from error
        handle = self._candidates.register(
            EvidenceKind.SOURCE_RANGE,
            SourceRangeEvidenceLocator(
                path=source.path,
                start_line=source.start_line,
                end_line=source.end_line,
                content_digest=source.content_digest,
            ),
        )
        return {
            "path": source.path,
            "revision": source.revision,
            "start_line": source.start_line,
            "end_line": source.end_line,
            "content": source.content,
            "truncated": source.truncated,
            "evidence_handle": handle,
        }

    @staticmethod
    def _append_orientation_hit(
        result: dict[str, list[dict[str, object]]],
        hit: RepositorySearchHit,
    ) -> None:
        common: dict[str, object] = {"label": hit.label, "score": hit.score}
        if hit.kind == "node" and isinstance(hit.ref, str):
            result["graph_nodes"].append(
                {**common, "node_id": hit.ref, "path": hit.source_path}
            )
        elif hit.kind == "community" and isinstance(hit.ref, dict):
            community_id = hit.ref.get("community_id")
            if isinstance(community_id, int) and not isinstance(community_id, bool):
                result["communities"].append({**common, "community_id": community_id})
        elif hit.kind == "file" and isinstance(hit.ref, str):
            result["files"].append({**common, "path": hit.ref})
        elif hit.kind == "symbol" and isinstance(hit.ref, str):
            result["symbols"].append(
                {
                    **common,
                    "symbol_id": hit.ref,
                    "path": hit.source_path,
                }
            )


def _path_mismatch_tool_error(
    error: FileIndexPathMismatchError,
) -> ToolExecutionError:
    return ToolExecutionError(
        str(error),
        details={
            "kind": "file_index_path_mismatch",
            "requested_path": error.requested_path,
            "closest_valid_paths": list(error.closest_valid_paths),
        },
    )


def build_worker_navigation_tools(
    navigator: RepositoryNavigator,
    candidates: EvidenceCandidateRegistry,
) -> ToolExecutor:
    """Bind the curated worker repository surface in deterministic order."""
    adapter = WorkerNavigationTools(navigator, candidates)
    tools = [
        LLMTool.bind(
            name="orient_repository",
            description=(
                "PRIMARY ORIENTATION TOOL. Use when a concept, responsibility, "
                "workflow, or behavior is known but its exact source file or symbol "
                "is not. Returns "
                "ranked graph nodes, communities, files, and symbols with stable IDs. "
                "Follow promising graph results with inspect_graph_node or "
                "inspect_graph_community, then verify behavioral conclusions in "
                "source. "
                "Do not use for an exact known literal or source location."
            ),
            arguments_type=_OrientRepositoryArguments,
            handler=lambda value: adapter.orient_repository(value.query),
        ),
        LLMTool.bind(
            name="inspect_graph_node",
            description=(
                "GRAPH TRAVERSAL AND SOURCE BRIDGE. Use a node_id returned by a "
                "repository or graph tool. Returns deterministic node facts, a "
                "bounded neighborhood, source file/symbol bridges, communities, and "
                "a graph evidence handle. Next inspect relevant source; graph "
                "structure alone is not proof of runtime behavior."
            ),
            arguments_type=_InspectGraphNodeArguments,
            handler=lambda value: adapter.inspect_graph_node(value.node_id),
        ),
        LLMTool.bind(
            name="inspect_graph_community",
            description=(
                "GRAPH AREA EXPLORATION. Use a community_id from orientation when a "
                "concept spans a related area. Returns bounded members and internal/"
                "cross-community relationships plus a graph evidence handle. Next "
                "select node IDs for inspect_graph_node and verify behavior in source."
            ),
            arguments_type=_InspectGraphCommunityArguments,
            handler=lambda value: adapter.inspect_graph_community(value.community_id),
        ),
        LLMTool.bind(
            name="trace_graph_path",
            description=(
                "KNOWN-NODE RELATIONSHIP TRACE. Use only when two graph node IDs are "
                "already known and their deterministic structural connection matters. "
                "Returns a bounded shortest path with actual edge directions. Next "
                "inspect important nodes and verify behavioral conclusions in source."
            ),
            arguments_type=_TraceGraphPathArguments,
            handler=lambda value: adapter.trace_graph_path(
                value.source_node_id,
                value.target_node_id,
            ),
        ),
        LLMTool.bind(
            name="list_files",
            description=(
                "CANONICAL FILEINDEX BROWSING. Return bounded valid repository paths "
                "from the pinned FileIndex. Optionally restrict by a normalized path "
                "prefix or an existing graph node and its one-hop neighbors. Use this "
                "when the repository area is known but the exact indexed path is not."
            ),
            arguments_type=_ListFilesArguments,
            handler=lambda value: adapter.list_files(
                value.path_prefix,
                value.graph_node_id,
                value.limit,
            ),
        ),
        LLMTool.bind(
            name="inspect_file",
            description=(
                "KNOWN-FILE INSPECTION AND BRIDGE. Use when an exact repository path "
                "is "
                "already known. The path must exactly match the pinned FileIndex. "
                "Returns file metadata, indexed symbols, graph node IDs, "
                "and a file evidence handle. Next inspect a symbol for implementation "
                "detail or a graph node for structural context. Do not use file "
                "browsing "
                "or inspection as a substitute for orient_repository when the relevant "
                "repository area is unknown."
            ),
            arguments_type=_InspectFileArguments,
            handler=lambda value: adapter.inspect_file(value.path),
        ),
        LLMTool.bind(
            name="find_symbol",
            description=(
                "KNOWN-SYMBOL LOOKUP. Use when a class, function, type, or other "
                "symbol name is known or strongly suspected, optionally in a known "
                "exact FileIndex path. "
                "Returns stable symbol IDs. Next inspect a selected result with "
                "inspect_symbol; use orient_repository for open-ended concepts."
            ),
            arguments_type=_FindSymbolArguments,
            handler=lambda value: adapter.find_symbol(value.query, value.path),
        ),
        LLMTool.bind(
            name="inspect_symbol",
            description=(
                "IMPLEMENTATION VERIFICATION. Use a stable symbol_id returned by a "
                "repository tool. Returns bounded exact source, graph associations, "
                "and a symbol evidence handle. Use this for substantive implementation "
                "claims. "
                "Follow graph associations only when additional structural context is "
                "needed."
            ),
            arguments_type=_InspectSymbolArguments,
            handler=lambda value: adapter.inspect_symbol(value.symbol_id),
        ),
        LLMTool.bind(
            name="find_source_text",
            description=(
                "SOURCE SEARCH / VERIFICATION. Use for a known literal, configuration "
                "value, error message, method name, or concrete phrase after candidate "
                "repository areas are known, or when the exact search target is "
                "already "
                "known. Any paths must exactly match the pinned FileIndex. Returns "
                "bounded line-addressable matches. Next read relevant "
                "matches with read_source_range. Do not use as the default open-ended "
                "repository orientation mechanism; use orient_repository when the "
                "implementation area is unknown."
            ),
            arguments_type=_FindSourceTextArguments,
            handler=lambda value: adapter.find_source_text(value.query, value.paths),
        ),
        LLMTool.bind(
            name="read_source_range",
            description=(
                "EXACT SOURCE EVIDENCE. Read one exact bounded line range from a known "
                "FileIndex path. Returns revision-bound source and a transient "
                "evidence handle. Next pass supporting handles to record_evidence."
            ),
            arguments_type=_ReadSourceRangeArguments,
            handler=lambda value: adapter.read_source_range(
                value.path,
                value.start_line,
                value.end_line,
            ),
        ),
    ]
    return ToolExecutor(tools, handled_errors=(ValueError, KeyError, RepositoryError))


__all__ = [
    "WORKER_REPOSITORY_TOOL_IDS",
    "EvidenceCandidate",
    "EvidenceCandidateRegistry",
    "WorkerNavigationTools",
    "build_worker_navigation_tools",
]
