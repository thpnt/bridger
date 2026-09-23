"""Local stdio adapter for Bridger's two consumption tools."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from bridger.graph.enrichment.errors import InvalidGraphEnrichment
from bridger.graph.errors import InvalidGraphSnapshot
from bridger.navigation.bootstrap import load_bridger_navigator
from bridger.navigation.bridger import BridgerNavigator
from bridger.presentation import render_intelligence_markdown
from bridger.repository.errors import RepositoryError
from bridger.repository.service import resolve_repository
from bridger.repository_brain.loader import RepositoryBrainLoadError


@dataclass
class _State:
    repository_root: Path
    navigator: BridgerNavigator | None = None


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
            "Use understand for repository orientation and impact after identifying "
            "exact symbols. Source code remains authoritative for exact implementation."
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

    return server


def run_mcp_server(requested_repository: Path) -> None:
    """Resolve one Git root, then serve only MCP messages on stdout."""
    try:
        repository_root = resolve_repository(requested_repository).root_path
    except RepositoryError as error:
        print(f"bridger mcp: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    create_mcp_server(repository_root).run("stdio")
