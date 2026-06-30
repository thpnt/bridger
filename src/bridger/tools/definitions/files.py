from typing import Annotated

from agents import RunContextWrapper, function_tool
from pydantic import Field

from bridger.tools.context import BridgerToolContext
from bridger.tools.errors import serialize_tool_call
from bridger.tools.models import FileFilters, GrepFilters


@function_tool
def list_files(
    ctx: RunContextWrapper[BridgerToolContext], filters: FileFilters
) -> dict[str, object]:
    """List safe indexed files using optional mechanical filters."""
    return serialize_tool_call(lambda: ctx.context.file_index.list_files(filters))


@function_tool
def list_tree(
    ctx: RunContextWrapper[BridgerToolContext],
    path_prefix: Annotated[
        str | None, Field(description="Repository-relative path prefix")
    ] = None,
    depth: Annotated[int, Field(ge=1, le=10)] = 3,
    limit: Annotated[int | None, Field(ge=1)] = None,
) -> dict[str, object]:
    """Derive a bounded directory tree from safe indexed paths."""
    return serialize_tool_call(
        lambda: ctx.context.file_index.list_tree(path_prefix, depth, limit)
    )


@function_tool
def search_paths(
    ctx: RunContextWrapper[BridgerToolContext],
    query: Annotated[str, Field(min_length=1, description="Path substring to find")],
    limit: Annotated[int | None, Field(ge=1)] = None,
) -> dict[str, object]:
    """Search safe indexed repository paths by substring."""
    return serialize_tool_call(
        lambda: ctx.context.file_index.search_paths(query, limit)
    )


@function_tool
def validate_paths(
    ctx: RunContextWrapper[BridgerToolContext],
    paths: Annotated[list[str], Field(min_length=1, max_length=100)],
) -> dict[str, object]:
    """Report whether repository-relative paths are safe indexed files."""
    return serialize_tool_call(lambda: ctx.context.file_index.validate_paths(paths))


@function_tool
def read_file_excerpt(
    ctx: RunContextWrapper[BridgerToolContext],
    path: Annotated[str, Field(min_length=1, description="Safe indexed file path")],
    start_line: Annotated[int | None, Field(ge=1)] = None,
    end_line: Annotated[int | None, Field(ge=1)] = None,
) -> dict[str, object]:
    """Read a bounded, 1-based line excerpt from a safe indexed file."""
    return serialize_tool_call(
        lambda: ctx.context.file_read.read_excerpt(path, start_line, end_line)
    )


@function_tool
def grep_contents(
    ctx: RunContextWrapper[BridgerToolContext],
    query: Annotated[str, Field(min_length=1, description="Literal text to find")],
    filters: GrepFilters,
) -> dict[str, object]:
    """Find literal text with line provenance across safe indexed files."""
    return serialize_tool_call(lambda: ctx.context.search.grep(query, filters))
