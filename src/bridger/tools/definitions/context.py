from typing import Annotated

from agents import RunContextWrapper, function_tool
from pydantic import Field

from bridger.tools.context import BridgerToolContext
from bridger.tools.errors import serialize_tool_call


@function_tool
def inspect_manifest(
    ctx: RunContextWrapper[BridgerToolContext],
    path: Annotated[str, Field(min_length=1, description="Indexed manifest path")],
) -> dict[str, object]:
    """Return mechanically parsed facts for an indexed manifest."""
    return serialize_tool_call(lambda: ctx.context.repo_context.inspect_manifest(path))


@function_tool
def list_config_files(ctx: RunContextWrapper[BridgerToolContext]) -> dict[str, object]:
    """List detected safe configuration files and their kinds."""
    return serialize_tool_call(ctx.context.repo_context.list_config_files)


@function_tool
def list_docs_files(ctx: RunContextWrapper[BridgerToolContext]) -> dict[str, object]:
    """List detected safe documentation files and their kinds."""
    return serialize_tool_call(ctx.context.repo_context.list_docs_files)


@function_tool
def list_instruction_files(
    ctx: RunContextWrapper[BridgerToolContext],
) -> dict[str, object]:
    """List detected safe instruction files and their kinds."""
    return serialize_tool_call(ctx.context.repo_context.list_instruction_files)


@function_tool
def list_ci_files(ctx: RunContextWrapper[BridgerToolContext]) -> dict[str, object]:
    """List detected safe CI files and their kinds."""
    return serialize_tool_call(ctx.context.repo_context.list_ci_files)
