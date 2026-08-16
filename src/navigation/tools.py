"""Explicit LLM-callable adapters over a bound RepositoryNavigator."""

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from llm.tools import LLMTool, ToolExecutor
from models.enrichment import EnrichmentTargetReference, EnrichmentTargetType
from models.files import ContentType, ReadMode
from models.navigation import GraphDirection, RepositorySearchKind
from models.symbols import SymbolKind
from navigation.navigator import (
    DEFAULT_LIST_LIMIT,
    DEFAULT_MAX_EDGES,
    DEFAULT_MAX_HYPEREDGES,
    DEFAULT_MAX_NODES,
    DEFAULT_RESULT_LIMIT,
    MAX_CONTEXT_LINES,
    MAX_EVIDENCE_BYTES,
    MAX_FILE_RANGES,
    MAX_GRAPH_DEPTH,
    MAX_GRAPH_EDGES,
    MAX_GRAPH_NODES,
    MAX_LIST_LIMIT,
    MAX_RANGE_LINES,
    MAX_RESULT_LIMIT,
    SOURCE_SEARCH_MAX_FILES,
    RepositoryNavigator,
)
from repository.errors import RepositoryError


def _repository_relative_path(value: str) -> str:
    if (
        value.startswith("/")
        or value in {"", "."}
        or value.startswith("./")
        or value.endswith("/")
        or "/./" in value
        or "//" in value
        or ".." in value.split("/")
    ):
        raise ValueError("path must be a normalized repository-relative path")
    return value


RepositoryRelativePath = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(_repository_relative_path),
]
RelationName = Annotated[str, Field(min_length=1)]


class _ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _SearchRepositoryArguments(_ToolArguments):
    query: str = Field(min_length=1, description="Entity name or concept to locate.")
    kinds: list[RepositorySearchKind] | None = Field(
        default=None,
        description="Optional entity kinds to include.",
    )
    limit: int = Field(default=DEFAULT_RESULT_LIMIT, ge=1, le=MAX_RESULT_LIMIT)
    min_score: float = Field(default=40, ge=0, le=100)


class _GetGraphEntityArguments(_ToolArguments):
    target_type: EnrichmentTargetType
    target_ref: EnrichmentTargetReference = Field(
        description="Existing target identity appropriate for target_type."
    )
    max_members: int = Field(default=DEFAULT_MAX_NODES, ge=1, le=MAX_GRAPH_NODES)


class _GraphNeighborsArguments(_ToolArguments):
    node_id: str = Field(min_length=1)
    direction: GraphDirection = "both"
    relations: list[RelationName] | None = None
    max_nodes: int = Field(default=DEFAULT_MAX_NODES, ge=1, le=MAX_GRAPH_NODES)
    max_edges: int = Field(default=DEFAULT_MAX_EDGES, ge=1, le=MAX_GRAPH_EDGES)
    max_hyperedges: int = Field(
        default=DEFAULT_MAX_HYPEREDGES,
        ge=1,
        le=MAX_RESULT_LIMIT,
    )


class _GraphPathArguments(_ToolArguments):
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    direction: GraphDirection = "outgoing"
    relations: list[RelationName] | None = None
    max_depth: int = Field(default=MAX_GRAPH_DEPTH, ge=1, le=MAX_GRAPH_DEPTH)
    max_nodes: int = Field(default=DEFAULT_MAX_NODES, ge=1, le=MAX_GRAPH_NODES)


class _GraphSubgraphArguments(_ToolArguments):
    node_id: str = Field(min_length=1)
    depth: int = Field(default=2, ge=1, le=MAX_GRAPH_DEPTH)
    direction: GraphDirection = "both"
    relations: list[RelationName] | None = None
    max_nodes: int = Field(default=DEFAULT_MAX_NODES, ge=1, le=MAX_GRAPH_NODES)
    max_edges: int = Field(default=DEFAULT_MAX_EDGES, ge=1, le=MAX_GRAPH_EDGES)
    max_hyperedges: int = Field(
        default=DEFAULT_MAX_HYPEREDGES,
        ge=1,
        le=MAX_RESULT_LIMIT,
    )


class _GraphCommunityArguments(_ToolArguments):
    community_id: int = Field(ge=0)
    max_nodes: int = Field(default=DEFAULT_MAX_NODES, ge=1, le=MAX_GRAPH_NODES)
    max_edges: int = Field(default=DEFAULT_MAX_EDGES, ge=1, le=MAX_GRAPH_EDGES)


class _LimitArguments(_ToolArguments):
    limit: int = Field(default=DEFAULT_RESULT_LIMIT, ge=1, le=MAX_RESULT_LIMIT)


class _NodeArguments(_ToolArguments):
    node_id: str = Field(min_length=1)


class _PathArguments(_ToolArguments):
    path: RepositoryRelativePath


class _SymbolArguments(_ToolArguments):
    symbol_id: str = Field(min_length=1)


class _ListFilesArguments(_ToolArguments):
    path_prefix: str | None = Field(default=None, min_length=1)
    content_types: list[ContentType] | None = None
    read_modes: list[ReadMode] | None = None
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)


class _FileOverviewArguments(_PathArguments):
    max_symbols: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)
    max_graph_nodes: int = Field(
        default=DEFAULT_LIST_LIMIT,
        ge=1,
        le=MAX_GRAPH_NODES,
    )


class _ListSymbolsArguments(_ToolArguments):
    path: RepositoryRelativePath | None = None
    kinds: list[SymbolKind] | None = None
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)


class _SearchSymbolsArguments(_ToolArguments):
    query: str = Field(min_length=1)
    path: RepositoryRelativePath | None = None
    kinds: list[SymbolKind] | None = None
    limit: int = Field(default=DEFAULT_RESULT_LIMIT, ge=1, le=MAX_RESULT_LIMIT)
    min_score: float = Field(default=40, ge=0, le=100)


class _SearchSourceArguments(_ToolArguments):
    query: str = Field(min_length=1, description="Literal text or regular expression.")
    regex: bool = False
    paths: list[RepositoryRelativePath] | None = None
    context_lines: int = Field(default=2, ge=0, le=MAX_CONTEXT_LINES)
    limit: int = Field(default=DEFAULT_RESULT_LIMIT, ge=1, le=MAX_RESULT_LIMIT)
    max_files: int = Field(
        default=SOURCE_SEARCH_MAX_FILES, ge=1, le=SOURCE_SEARCH_MAX_FILES
    )

    @model_validator(mode="after")
    def validate_regular_expression(self) -> "_SearchSourceArguments":
        if self.regex:
            try:
                re.compile(self.query)
            except re.error as error:
                raise ValueError("query must be a valid regular expression") from error
        return self


class _ReadSymbolArguments(_SymbolArguments):
    context_lines: int = Field(default=2, ge=0, le=MAX_CONTEXT_LINES)
    max_bytes: int = Field(default=64 * 1024, ge=1, le=MAX_EVIDENCE_BYTES)


class _LineRange(_ToolArguments):
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> "_LineRange":
        if self.end_line < self.start_line:
            raise ValueError("end_line must not be before start_line")
        if self.end_line - self.start_line + 1 > MAX_RANGE_LINES:
            raise ValueError(f"line range is limited to {MAX_RANGE_LINES} lines")
        return self


class _ReadFileRangesArguments(_PathArguments):
    ranges: list[_LineRange] = Field(min_length=1, max_length=MAX_FILE_RANGES)
    max_bytes_per_range: int = Field(
        default=64 * 1024,
        ge=1,
        le=MAX_EVIDENCE_BYTES,
    )


class _ReadAroundMatchArguments(_PathArguments):
    line_number: int = Field(ge=1)
    context_lines: int = Field(default=5, ge=0, le=MAX_CONTEXT_LINES)
    max_bytes: int = Field(default=64 * 1024, ge=1, le=MAX_EVIDENCE_BYTES)


def build_navigation_tools(navigator: RepositoryNavigator) -> ToolExecutor:
    """Bind the explicit Layer 6 tool set to one immutable navigator context."""
    tools = [
        LLMTool.bind(
            name="search_repository",
            description=(
                "Locate graph entities, communities, files, and symbols by structured "
                "repository metadata; this does not search source text."
            ),
            arguments_type=_SearchRepositoryArguments,
            handler=lambda value: navigator.search_repository(
                value.query,
                kinds=value.kinds,
                limit=value.limit,
                min_score=value.min_score,
            ),
        ),
        LLMTool.bind(
            name="get_graph_entity",
            description=(
                "Inspect one existing graph target and return deterministic facts plus "
                "separate matching enrichment."
            ),
            arguments_type=_GetGraphEntityArguments,
            handler=lambda value: navigator.get_graph_entity(
                value.target_type,
                value.target_ref,
                max_members=value.max_members,
            ),
        ),
        LLMTool.bind(
            name="get_graph_neighbors",
            description="Return a bounded one-hop graph neighborhood around a node.",
            arguments_type=_GraphNeighborsArguments,
            handler=lambda value: navigator.get_graph_neighbors(
                value.node_id,
                direction=value.direction,
                relations=value.relations,
                max_nodes=value.max_nodes,
                max_edges=value.max_edges,
                max_hyperedges=value.max_hyperedges,
            ),
        ),
        LLMTool.bind(
            name="get_graph_path",
            description=(
                "Find one bounded deterministic shortest path between graph nodes."
            ),
            arguments_type=_GraphPathArguments,
            handler=lambda value: navigator.get_graph_path(
                value.source_node_id,
                value.target_node_id,
                direction=value.direction,
                relations=value.relations,
                max_depth=value.max_depth,
                max_nodes=value.max_nodes,
            ),
        ),
        LLMTool.bind(
            name="get_graph_subgraph",
            description=(
                "Materialize a bounded graph neighborhood to the requested depth."
            ),
            arguments_type=_GraphSubgraphArguments,
            handler=lambda value: navigator.get_graph_subgraph(
                value.node_id,
                depth=value.depth,
                direction=value.direction,
                relations=value.relations,
                max_nodes=value.max_nodes,
                max_edges=value.max_edges,
                max_hyperedges=value.max_hyperedges,
            ),
        ),
        LLMTool.bind(
            name="get_graph_community",
            description=(
                "Inspect bounded community members plus internal and cross-community "
                "edges."
            ),
            arguments_type=_GraphCommunityArguments,
            handler=lambda value: navigator.get_graph_community(
                value.community_id,
                max_nodes=value.max_nodes,
                max_edges=value.max_edges,
            ),
        ),
        LLMTool.bind(
            name="get_graph_central_nodes",
            description=(
                "Return the persisted central graph nodes in deterministic order."
            ),
            arguments_type=_LimitArguments,
            handler=lambda value: navigator.get_graph_central_nodes(limit=value.limit),
        ),
        LLMTool.bind(
            name="graph_to_file",
            description=(
                "Resolve a graph node to its canonical indexed source file, if any."
            ),
            arguments_type=_NodeArguments,
            handler=lambda value: navigator.graph_to_file(value.node_id),
        ),
        LLMTool.bind(
            name="graph_to_symbols",
            description="Resolve a graph node to all exact indexed symbol matches.",
            arguments_type=_NodeArguments,
            handler=lambda value: navigator.graph_to_symbols(value.node_id),
        ),
        LLMTool.bind(
            name="file_to_graph",
            description="Return graph nodes exactly associated with an indexed file.",
            arguments_type=_PathArguments,
            handler=lambda value: navigator.file_to_graph(value.path),
        ),
        LLMTool.bind(
            name="symbol_to_graph",
            description="Return graph nodes exactly associated with an indexed symbol.",
            arguments_type=_SymbolArguments,
            handler=lambda value: navigator.symbol_to_graph(value.symbol_id),
        ),
        LLMTool.bind(
            name="list_files",
            description="List a bounded filtered view of canonical indexed files.",
            arguments_type=_ListFilesArguments,
            handler=lambda value: navigator.list_files(
                path_prefix=value.path_prefix,
                content_types=value.content_types,
                read_modes=value.read_modes,
                limit=value.limit,
            ),
        ),
        LLMTool.bind(
            name="get_file_overview",
            description=(
                "Inspect one indexed file and its exact symbol and graph associations."
            ),
            arguments_type=_FileOverviewArguments,
            handler=lambda value: navigator.get_file_overview(
                value.path,
                max_symbols=value.max_symbols,
                max_graph_nodes=value.max_graph_nodes,
            ),
        ),
        LLMTool.bind(
            name="list_symbols",
            description=(
                "List bounded canonical symbols, optionally filtered by file or kind."
            ),
            arguments_type=_ListSymbolsArguments,
            handler=lambda value: navigator.list_symbols(
                path=value.path,
                kinds=value.kinds,
                limit=value.limit,
            ),
        ),
        LLMTool.bind(
            name="search_symbols",
            description=(
                "Search indexed symbol names and qualified names with bounded results."
            ),
            arguments_type=_SearchSymbolsArguments,
            handler=lambda value: navigator.search_symbols(
                value.query,
                path=value.path,
                kinds=value.kinds,
                limit=value.limit,
                min_score=value.min_score,
            ),
        ),
        LLMTool.bind(
            name="search_source_content",
            description=(
                "Search authorized repository source text and return bounded "
                "line-addressable matches."
            ),
            arguments_type=_SearchSourceArguments,
            handler=lambda value: navigator.search_source_content(
                value.query,
                regex=value.regex,
                paths=value.paths,
                context_lines=value.context_lines,
                limit=value.limit,
                max_files=value.max_files,
            ),
        ),
        LLMTool.bind(
            name="read_symbol_excerpt",
            description="Read a bounded exact-source excerpt around an indexed symbol.",
            arguments_type=_ReadSymbolArguments,
            handler=lambda value: navigator.read_symbol_excerpt(
                value.symbol_id,
                context_lines=value.context_lines,
                max_bytes=value.max_bytes,
            ),
        ),
        LLMTool.bind(
            name="read_file_ranges",
            description=(
                "Read one or more bounded exact line ranges from an indexed file."
            ),
            arguments_type=_ReadFileRangesArguments,
            handler=lambda value: navigator.read_file_ranges(
                value.path,
                [(item.start_line, item.end_line) for item in value.ranges],
                max_bytes_per_range=value.max_bytes_per_range,
            ),
        ),
        LLMTool.bind(
            name="read_around_match",
            description=(
                "Read a bounded exact-source window around a line-addressable match."
            ),
            arguments_type=_ReadAroundMatchArguments,
            handler=lambda value: navigator.read_around_match(
                value.path,
                value.line_number,
                context_lines=value.context_lines,
                max_bytes=value.max_bytes,
            ),
        ),
    ]
    return ToolExecutor(
        tools,
        handled_errors=(ValueError, KeyError, RepositoryError),
    )


__all__ = ["build_navigation_tools"]
