from typing import Annotated

from agents import RunContextWrapper, function_tool
from pydantic import Field

from bridger.tools.context import BridgerToolContext
from bridger.tools.errors import serialize_tool_call


@function_tool
def get_file_overview(
    ctx: RunContextWrapper[BridgerToolContext],
    path: Annotated[str, Field(min_length=1, description="Safe indexed file path")],
) -> dict[str, object]:
    """Return factual metadata, symbols, imports, and reverse imports for one file."""

    def compose() -> dict[str, object]:
        normalized = ctx.context.path_safety.validate_file(path)
        metadata = ctx.context.file_index.get_file(normalized)
        symbols = ctx.context.symbols.list_for_path(normalized)
        imports = ctx.context.graph.imports(normalized)
        imported_by = ctx.context.graph.reverse_imports(normalized)
        return {
            "path": normalized,
            "file": metadata.model_dump(mode="json"),
            "symbols": symbols["symbols"],
            "symbols_total": symbols["total_matches"],
            "symbols_limit_applied": symbols["limit_applied"],
            "symbols_truncated": symbols["truncated"],
            "imports": imports["imports"],
            "imports_total": imports["total_matches"],
            "imports_limit_applied": imports["limit_applied"],
            "imports_truncated": imports["truncated"],
            "imported_by": imported_by["imported_by"],
            "imported_by_total": imported_by["total_matches"],
            "imported_by_limit_applied": imported_by["limit_applied"],
            "imported_by_truncated": imported_by["truncated"],
            "source_artifacts": [
                "file-index.json",
                "symbol-index.json",
                "repo-graph.json",
            ],
        }

    return serialize_tool_call(compose)


@function_tool
def get_graph_neighbors(
    ctx: RunContextWrapper[BridgerToolContext],
    path: Annotated[str, Field(min_length=1, description="Safe indexed file path")],
) -> dict[str, object]:
    """Return bounded factual graph neighbors for one safe file."""
    return serialize_tool_call(lambda: ctx.context.graph.neighbors(path))


@function_tool
def get_reverse_imports(
    ctx: RunContextWrapper[BridgerToolContext],
    path: Annotated[str, Field(min_length=1, description="Safe indexed file path")],
) -> dict[str, object]:
    """List safe files that import the selected file."""
    return serialize_tool_call(lambda: ctx.context.graph.reverse_imports(path))


@function_tool
def list_file_imports(
    ctx: RunContextWrapper[BridgerToolContext],
    path: Annotated[str, Field(min_length=1, description="Safe indexed file path")],
) -> dict[str, object]:
    """List safe local files imported by the selected file."""
    return serialize_tool_call(lambda: ctx.context.graph.imports(path))


@function_tool
def list_declared_entrypoints(
    ctx: RunContextWrapper[BridgerToolContext],
) -> dict[str, object]:
    """List file entrypoints directly declared by manifests."""
    return serialize_tool_call(ctx.context.graph.declared_entrypoints)


@function_tool
def inspect_graph_summary(
    ctx: RunContextWrapper[BridgerToolContext],
) -> dict[str, object]:
    """Return deterministic graph counts and bounded summary facts."""
    return serialize_tool_call(ctx.context.graph_summary.inspect)
