from typing import Annotated

from agents import RunContextWrapper, function_tool
from pydantic import Field

from bridger.tools.context import BridgerToolContext
from bridger.tools.errors import serialize_tool_call


@function_tool
def search_symbols(
    ctx: RunContextWrapper[BridgerToolContext],
    query: Annotated[str, Field(min_length=1, description="Symbol text to find")],
    limit: Annotated[int | None, Field(ge=1)] = None,
) -> dict[str, object]:
    """Search syntactic symbol names and declarations."""
    return serialize_tool_call(lambda: ctx.context.symbols.search(query, limit))


@function_tool
def list_symbols(
    ctx: RunContextWrapper[BridgerToolContext],
    path: Annotated[str, Field(min_length=1, description="Safe indexed file path")],
    limit: Annotated[int | None, Field(ge=1)] = None,
) -> dict[str, object]:
    """List bounded syntactic symbols declared in one safe file."""
    return serialize_tool_call(lambda: ctx.context.symbols.list_for_path(path, limit))


@function_tool
def get_symbol(
    ctx: RunContextWrapper[BridgerToolContext],
    symbol_id: Annotated[str, Field(min_length=1)],
) -> dict[str, object]:
    """Return one syntactic symbol record by stable ID."""
    return serialize_tool_call(lambda: ctx.context.symbols.get_result(symbol_id))


@function_tool
def read_symbol_excerpt(
    ctx: RunContextWrapper[BridgerToolContext],
    symbol_id: Annotated[str, Field(min_length=1)],
    context_lines: Annotated[int, Field(ge=0, le=100)] = 5,
) -> dict[str, object]:
    """Return symbol facts and a bounded source excerpt around its line range."""

    def compose() -> dict[str, object]:
        symbol = ctx.context.symbols.get(symbol_id)
        metadata = ctx.context.file_index.get_file(symbol.path)
        start = max(1, symbol.line_start - context_lines)
        end = min(metadata.line_count, symbol.line_end + context_lines)
        excerpt = ctx.context.file_read.read_excerpt(symbol.path, start, end)
        return {
            "source_artifact": "symbol-index.json",
            "symbol": symbol.model_dump(mode="json"),
            "excerpt": excerpt,
        }

    return serialize_tool_call(compose)
