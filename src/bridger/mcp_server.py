"""Local stdio adapter for Bridger consumption and graph navigation tools."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from bridger.contracts.enrichment import EnrichmentTargetReference, EnrichmentTargetType
from bridger.contracts.navigation import (
    CompositeEntityView,
    GraphCommunityView,
    GraphDirection,
    GraphTraversalView,
    RepositorySearchHit,
    RepositorySearchKind,
)
from bridger.graph.enrichment.errors import InvalidGraphEnrichment
from bridger.graph.errors import InvalidGraphSnapshot
from bridger.navigation.bootstrap import load_bridger_navigator
from bridger.navigation.bridger import BridgerNavigator
from bridger.navigation.navigator import (
    DEFAULT_MAX_EDGES,
    DEFAULT_MAX_HYPEREDGES,
    DEFAULT_MAX_NODES,
    DEFAULT_RESULT_LIMIT,
    MAX_GRAPH_DEPTH,
    RepositoryNavigator,
)
from bridger.presentation import render_intelligence_markdown
from bridger.repository.errors import RepositoryError
from bridger.repository.service import resolve_repository
from bridger.repository_brain.loader import RepositoryBrainLoadError


@dataclass
class _State:
    repository_root: Path
    navigator: BridgerNavigator | None = None


_Result = TypeVar("_Result")


def _get_navigator(state: _State) -> BridgerNavigator:
    if state.navigator is None:
        try:
            state.navigator = load_bridger_navigator(state.repository_root)
        except (
            ValueError,
            RepositoryError,
            RepositoryBrainLoadError,
            InvalidGraphSnapshot,
            InvalidGraphEnrichment,
        ) as error:
            raise ToolError(str(error)) from error
    return state.navigator


def _call_repository_tool(
    state: _State, operation: Callable[[RepositoryNavigator], _Result]
) -> _Result:
    repository = _get_navigator(state).repository_navigator
    try:
        return operation(repository)
    except (KeyError, RepositoryError, ValueError) as error:
        raise ToolError(str(error)) from error


def create_mcp_server(repository_root: Path) -> MCPServer[_State]:
    """Build one MCP server pinned to an already resolved repository root."""

    @asynccontextmanager
    async def lifespan(_server: MCPServer[_State]) -> AsyncIterator[_State]:
        state = _State(repository_root)
        try:
            yield state
        finally:
            if state.navigator is not None:
                state.navigator.close()

    server = MCPServer[_State](
        "bridger",
        instructions=(
            "Use understand for semantic repository orientation and graph-native tools "
            "to discover structural relationships. Use impact after identifying exact "
            "symbols that may change. Source code remains authoritative for exact "
            "implementation behavior."
        ),
        lifespan=lifespan,
        log_level="WARNING",
    )

    @server.tool(structured_output=False)
    async def understand(query: str, ctx: Context[_State]) -> str:
        """Retrieve authored Brain and immediate graph context for a question."""
        navigator = _get_navigator(ctx.request_context.lifespan_context)
        try:
            result = navigator.understand(query)
        except ValueError as error:
            raise ToolError(str(error)) from error
        return render_intelligence_markdown(result)

    @server.tool(structured_output=False)
    async def impact(symbols: list[str], ctx: Context[_State]) -> str:
        """Return potential impact for exact symbols, with ambiguity candidates."""
        navigator = _get_navigator(ctx.request_context.lifespan_context)
        try:
            result = navigator.impact(symbols)
        except ValueError as error:
            raise ToolError(str(error)) from error
        return render_intelligence_markdown(result)

    @server.tool(structured_output=True)
    async def query_graph(
        query: str, ctx: Context[_State]
    ) -> dict[str, JsonValue]:
        """Discover relevant graph nodes, relations, communities, and source locations.

        Use this natural-language entry point when exact graph IDs are not yet known.
        """
        result = _call_repository_tool(
            ctx.request_context.lifespan_context,
            lambda repository: repository.query_graph(query),
        )
        return {
            "context": result.context.model_dump(mode="json"),
            "truncated": result.truncated,
        }

    @server.tool(structured_output=True)
    async def search_repository(
        query: str,
        ctx: Context[_State],
        kinds: list[RepositorySearchKind] | None = None,
        limit: int = DEFAULT_RESULT_LIMIT,
        min_score: float = 40,
    ) -> list[RepositorySearchHit]:
        """Resolve a name or concept into deterministic repository entity candidates."""
        return _call_repository_tool(
            ctx.request_context.lifespan_context,
            lambda repository: repository.search_repository(
                query, kinds=kinds, limit=limit, min_score=min_score
            ),
        )

    @server.tool(structured_output=True)
    async def get_graph_entity(
        target_type: EnrichmentTargetType,
        target_ref: EnrichmentTargetReference,
        ctx: Context[_State],
        max_members: int = DEFAULT_MAX_NODES,
    ) -> CompositeEntityView:
        """Inspect one exact graph entity with deterministic data and enrichment."""
        return _call_repository_tool(
            ctx.request_context.lifespan_context,
            lambda repository: repository.get_graph_entity(
                target_type, target_ref, max_members=max_members
            ),
        )

    @server.tool(structured_output=True)
    async def get_graph_neighbors(
        node_id: str,
        ctx: Context[_State],
        direction: GraphDirection = "both",
        relations: list[str] | None = None,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
        max_hyperedges: int = DEFAULT_MAX_HYPEREDGES,
    ) -> GraphTraversalView:
        """Return a bounded immediate neighborhood with exact relation filters."""
        return _call_repository_tool(
            ctx.request_context.lifespan_context,
            lambda repository: repository.get_graph_neighbors(
                node_id,
                direction=direction,
                relations=relations,
                max_nodes=max_nodes,
                max_edges=max_edges,
                max_hyperedges=max_hyperedges,
            ),
        )

    @server.tool(structured_output=True)
    async def get_graph_subgraph(
        node_id: str,
        ctx: Context[_State],
        depth: int = 2,
        direction: GraphDirection = "both",
        relations: list[str] | None = None,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
        max_hyperedges: int = DEFAULT_MAX_HYPEREDGES,
    ) -> GraphTraversalView:
        """Explore a bounded multi-hop neighborhood around an exact graph node."""
        return _call_repository_tool(
            ctx.request_context.lifespan_context,
            lambda repository: repository.get_graph_subgraph(
                node_id,
                depth=depth,
                direction=direction,
                relations=relations,
                max_nodes=max_nodes,
                max_edges=max_edges,
                max_hyperedges=max_hyperedges,
            ),
        )

    @server.tool(structured_output=True)
    async def get_graph_path(
        source_node_id: str,
        target_node_id: str,
        ctx: Context[_State],
        direction: GraphDirection = "outgoing",
        relations: list[str] | None = None,
        max_depth: int = MAX_GRAPH_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
    ) -> GraphTraversalView:
        """Find one deterministic bounded shortest path between exact graph nodes.

        An empty result with ``truncated=false`` is conclusive within the requested
        topology; ``truncated=true`` means bounds prevented an exhaustive conclusion.
        """
        return _call_repository_tool(
            ctx.request_context.lifespan_context,
            lambda repository: repository.get_graph_path(
                source_node_id,
                target_node_id,
                direction=direction,
                relations=relations,
                max_depth=max_depth,
                max_nodes=max_nodes,
            ),
        )

    @server.tool(structured_output=True)
    async def list_graph_communities(
        ctx: Context[_State], limit: int = DEFAULT_RESULT_LIMIT
    ) -> list[CompositeEntityView]:
        """List persisted graph communities in their deterministic structural order."""
        return _call_repository_tool(
            ctx.request_context.lifespan_context,
            lambda repository: repository.list_graph_communities(limit=limit),
        )

    @server.tool(structured_output=True)
    async def get_graph_community(
        community_id: int,
        ctx: Context[_State],
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
    ) -> GraphCommunityView:
        """Inspect community members and internal and cross-community edges."""
        return _call_repository_tool(
            ctx.request_context.lifespan_context,
            lambda repository: repository.get_graph_community(
                community_id, max_nodes=max_nodes, max_edges=max_edges
            ),
        )

    return server


def run_mcp_server(requested_repository: Path) -> None:
    """Resolve one Git root, then serve only MCP messages on stdout."""
    try:
        repository_root = resolve_repository(requested_repository).root_path
    except RepositoryError as error:
        print(f"bridger mcp: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    create_mcp_server(repository_root).run("stdio")
