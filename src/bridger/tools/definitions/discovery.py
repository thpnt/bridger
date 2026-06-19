from agents import RunContextWrapper, function_tool

from bridger.tools.context import BridgerToolContext
from bridger.tools.errors import serialize_tool_call


@function_tool
def inspect_repo_discovery(
    ctx: RunContextWrapper[BridgerToolContext],
) -> dict[str, object]:
    """Return the factual repository discovery bootstrap manifest."""
    return serialize_tool_call(ctx.context.repo_discovery.inspect)
