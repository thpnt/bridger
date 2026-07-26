"""Standalone wrappers for the consolidated exploration service surface."""

from typing import Annotated

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, ConfigDict, Field

from bridger.tools.context import BridgerToolContext
from bridger.tools.errors import serialize_tool_call


class LineRangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


@function_tool
def inspect_repo_discovery(
    ctx: RunContextWrapper[BridgerToolContext],
) -> dict[str, object]:
    """Return compact, deterministic Git-inventory orientation facts."""
    files = ctx.context.file_index.artifact.files
    return {
        "ok": True,
        "status": "completed",
        "inventory": {"total_files": len(files)},
        "symbol_index": {"total_symbols": len(ctx.context.symbols.artifact.symbols)},
    }


@function_tool
def get_file_overview(
    ctx: RunContextWrapper[BridgerToolContext],
    path: Annotated[str, Field(min_length=1)],
    symbol_limit: Annotated[int, Field(ge=1, le=300)] = 100,
    symbol_cursor: str | None = None,
    import_limit: Annotated[int, Field(ge=1, le=300)] = 100,
    import_cursor: str | None = None,
) -> dict[str, object]:
    """Return bounded file metadata and symbol navigation facts."""

    def compose() -> dict[str, object]:
        item = ctx.context.file_index.get_file(path)
        symbols = ctx.context.symbols.list_for_path(path, symbol_limit, symbol_cursor)
        return {
            "path": item.path,
            "size_bytes": item.size_bytes,
            "total_lines": item.line_count,
            "symbols": symbols,
            "imports": {"total": 0, "items": [], "has_more": False},
            "warnings": [],
        }

    return serialize_tool_call(compose)


@function_tool
def search_with_context(
    ctx: RunContextWrapper[BridgerToolContext],
    query: Annotated[str, Field(min_length=1)],
    match_mode: str = "literal",
    case_sensitive: bool = False,
    path_prefix: str | None = None,
    file_pattern: str | None = None,
    before: Annotated[int, Field(ge=0, le=20)] = 3,
    after: Annotated[int, Field(ge=0, le=20)] = 3,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> dict[str, object]:
    """Search readable Git-inventory text with bounded surrounding context."""
    return serialize_tool_call(
        lambda: ctx.context.search.search_with_context(
            query,
            match_mode=match_mode,
            case_sensitive=case_sensitive,
            path_prefix=path_prefix,
            file_pattern=file_pattern,
            before=before,
            after=after,
            limit=limit,
            cursor=cursor,
        )
    )


@function_tool
def read_file_ranges(
    ctx: RunContextWrapper[BridgerToolContext],
    path: Annotated[str, Field(min_length=1)],
    ranges: Annotated[list[LineRangeInput], Field(min_length=1, max_length=10)],
) -> dict[str, object]:
    """Read normalized, inclusive, non-contiguous file ranges."""
    return serialize_tool_call(
        lambda: ctx.context.file_read.read_ranges(
            path, [item.model_dump() for item in ranges]
        )
    )


@function_tool
def read_around_match(
    ctx: RunContextWrapper[BridgerToolContext],
    path: Annotated[str, Field(min_length=1)],
    line: Annotated[int, Field(ge=1)],
    before: Annotated[int, Field(ge=0, le=100)] = 20,
    after: Annotated[int, Field(ge=0, le=100)] = 20,
) -> dict[str, object]:
    """Read one bounded context window around a source line."""
    return serialize_tool_call(
        lambda: ctx.context.file_read.read_around(path, line, before, after)
    )


@function_tool
def get_inspection_status(
    ctx: RunContextWrapper[BridgerToolContext],
    path: Annotated[str, Field(min_length=1)],
) -> dict[str, object]:
    """Report persisted factual inspection ranges for a file."""

    def compose() -> dict[str, object]:
        item = ctx.context.file_index.get_file(path)
        state = ctx.context.artifact_store.load_context_plan_working_state()
        file = next(
            (value for value in state.inspected_files if value.path == path), None
        )
        ranges = (
            []
            if file is None
            else [value.model_dump() for value in file.inspected_ranges]
        )
        return {
            "path": path,
            "total_lines": item.line_count,
            "inspected_ranges": ranges,
        }

    return serialize_tool_call(compose)
